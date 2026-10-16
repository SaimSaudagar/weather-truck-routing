import uuid
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone

from django.conf import settings
from django.core.cache import cache

from . import geo, hos, ranking
from .risk import Risk, assess
from .services import osrm, weather

ROUTE_NAMES = "ABC"


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _thin(coords, cum, min_gap_mi=0.25):
    """Drop geometry points closer than `min_gap_mi` apart. Keeps payloads small."""
    keep = [coords[0]]
    last = 0.0
    for c, d in zip(coords[1:-1], cum[1:-1]):
        if d - last >= min_gap_mi:
            keep.append(c)
            last = d
    keep.append(coords[-1])
    return [[round(x, 5), round(y, 5)] for x, y in keep]


def _slice(coords, cum, start, end):
    """Part of the line between two mileposts, endpoints interpolated."""
    lo = bisect_right(cum, start)
    hi = bisect_left(cum, end)
    return [geo.point_at(coords, cum, start), *coords[lo:hi], geo.point_at(coords, cum, end)]


def _drive_profile(route, cum, speed_cap_mph):
    """Cumulative driving seconds at every geometry vertex, with a truck speed cap."""
    out = [0.0]
    for i, seg in enumerate(route["segment_durations"]):
        miles = cum[i + 1] - cum[i]
        capped = miles / speed_cap_mph * 3600 if speed_cap_mph else 0
        out.append(out[-1] + max(seg, capped))
    return out


def _build_checkpoints(route, depart_ts, interval_mi, opts):
    coords = route["coords"]
    cum = geo.cumulative_miles(coords)
    drive = _drive_profile(route, cum, opts["speed_cap_mph"])
    total = cum[-1]

    marks = geo.sample_distances(total, interval_mi)
    checkpoints = []
    for i, mile in enumerate(marks):
        lon, lat = geo.point_at(coords, cum, mile)
        drive_s = geo.interpolate(cum, drive, mile)
        eta = depart_ts + hos.elapsed_for_drive(drive_s, opts["hos"])
        # each checkpoint speaks for the stretch of road closest to it
        start = 0 if i == 0 else (marks[i - 1] + mile) / 2
        end = total if i == len(marks) - 1 else (mile + marks[i + 1]) / 2
        checkpoints.append({
            "index": i,
            "mile": round(mile, 1),
            "lon": round(lon, 5),
            "lat": round(lat, 5),
            "eta_ts": eta,
            "covers": (start, end),
        })

    return {
        "coords": coords,
        "cum": cum,
        "total_mi": total,
        "drive_s": drive[-1],
        "checkpoints": checkpoints,
    }


def _summarize(name, built, depart_ts, series, load_lb, opts):
    risk_miles = {lvl.key: 0.0 for lvl in Risk}
    unscored = 0.0
    weighted = 0.0
    max_level = Risk.LOW
    segments = []
    checkpoints = []

    for cp in built["checkpoints"]:
        start, end = cp.pop("covers")
        miles = end - start
        wx = weather.at(weather.lookup(series, cp["lon"], cp["lat"]), cp["eta_ts"])
        a = assess(wx["wind_mph"], wx["rain_in_hr"], wx["snow_in_hr"], load_lb)

        if wx["in_forecast"]:
            risk_miles[a.level.key] += miles
            weighted += int(a.level) * miles
            max_level = max(max_level, a.level)
        else:
            unscored += miles

        if miles > 0:
            piece = _slice(built["coords"], built["cum"], start, end)
            segments.append({
                "level": a.level.key if wx["in_forecast"] else "unknown",
                "coords": _thin(piece, geo.cumulative_miles(piece)),
            })

        checkpoints.append({
            **cp,
            "eta": _iso(cp.pop("eta_ts")),
            "covers_mi": round(miles, 1),
            "weather": wx | {"time": _iso(wx["time"])},
            "risk": a.as_dict() if wx["in_forecast"] else {
                "level": "unknown", "score": None, "reasons": ["ETA is past the forecast range"],
            },
        })

    scored = built["total_mi"] - unscored
    trip_s = hos.elapsed_for_drive(built["drive_s"], opts["hos"])
    return {
        "id": name.lower(),
        "name": f"Route {name}",
        "distance_mi": round(built["total_mi"], 1),
        "drive_s": round(built["drive_s"]),
        "trip_s": round(trip_s),
        "arrival": _iso(depart_ts + trip_s),
        "hos_stops": hos.stops_for_drive(built["drive_s"], opts["hos"]),
        "risk_miles": {k: round(v, 1) for k, v in risk_miles.items()},
        "unscored_mi": round(unscored, 1),
        "avg_risk": round(weighted / scored, 3) if scored else 0.0,
        "max_level": int(max_level),
        "geometry": _thin(built["coords"], built["cum"]),
        "segments": segments,
        "checkpoints": checkpoints,
    }


def plan_trip(origin, destination, depart_ts, load_lb, interval_mi, use_hos=True):
    opts = {"hos": use_hos, "speed_cap_mph": settings.TRUCK_SPEED_CAP_MPH}

    raw = osrm.get_routes((origin["lon"], origin["lat"]), (destination["lon"], destination["lat"]))
    built = [_build_checkpoints(r, depart_ts, interval_mi, opts) for r in raw]

    # one weather fetch covering every checkpoint on every route
    points = [(cp["lon"], cp["lat"]) for b in built for cp in b["checkpoints"]]
    last_eta = max(cp["eta_ts"] for b in built for cp in b["checkpoints"])
    series = weather.get_series(points, depart_ts, last_eta)

    routes = [
        _summarize(ROUTE_NAMES[i], b, depart_ts, series, load_lb, opts)
        for i, b in enumerate(built)
    ]
    ordered, recommendation = ranking.rank(routes)

    plan_id = uuid.uuid4().hex[:12]
    plan = {
        "id": plan_id,
        "origin": origin,
        "destination": destination,
        "departure": _iso(depart_ts),
        "load_lb": load_lb,
        "interval_mi": interval_mi,
        "hos": use_hos,
        "routes": ordered,
        "recommendation": recommendation,
    }
    # the heatmap endpoint needs the route shapes; keep them around for a while
    cache.set(f"plan:{plan_id}", {
        "depart_ts": depart_ts,
        "load_lb": load_lb,
        "lines": [r["geometry"] for r in ordered],
    }, settings.PLAN_CACHE_SECONDS)
    return plan

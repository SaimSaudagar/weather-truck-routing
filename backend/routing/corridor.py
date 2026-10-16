"""
Weather heatmap along the trip corridor.

A grid of points is laid over the bounding box of all routes and only the
ones within CORRIDOR_MI of some route are kept. Grid spacing grows with the
trip length so a cross-country run doesn't turn into thousands of forecast
lookups. All 49 hourly frames (0..48h) are computed server side and sent at
once, so the slider on the frontend never waits on the network.
"""
import math
from collections import defaultdict

from . import geo
from .risk import Risk, assess, continuous_score
from .services import weather

CORRIDOR_MI = 40
TARGET_POINTS = 250
MIN_SPACING_MI = 8
HOURS = 48


def _anchors(lines, every_mi=10):
    pts = []
    for line in lines:
        cum = geo.cumulative_miles(line)
        d = 0.0
        while d <= cum[-1]:
            pts.append(geo.point_at(line, cum, d))
            d += every_mi
        pts.append(tuple(line[-1]))
    return pts


def _bucket(points):
    grid = defaultdict(list)
    for p in points:
        grid[(math.floor(p[0]), math.floor(p[1]))].append(p)
    return grid


def _near_route(p, buckets, radius):
    cx, cy = math.floor(p[0]), math.floor(p[1])
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for q in buckets.get((cx + dx, cy + dy), ()):
                if geo.haversine_mi(p, q) <= radius:
                    return True
    return False


def build_grid(lines, corridor_mi=CORRIDOR_MI, target=TARGET_POINTS):
    anchors = _anchors(lines)
    buckets = _bucket(anchors)

    longest = max(geo.cumulative_miles(l)[-1] for l in lines)
    spacing = max(MIN_SPACING_MI, math.sqrt(longest * corridor_mi * 2 / target))

    min_lon = min(p[0] for p in anchors)
    max_lon = max(p[0] for p in anchors)
    min_lat = min(p[1] for p in anchors)
    max_lat = max(p[1] for p in anchors)
    mid_lat = (min_lat + max_lat) / 2

    for _ in range(5):
        dlat = spacing / 69.0
        dlon = spacing / (69.0 * max(math.cos(math.radians(mid_lat)), 0.2))
        pad_lat = corridor_mi / 69.0
        pad_lon = corridor_mi / (69.0 * max(math.cos(math.radians(mid_lat)), 0.2))

        points = []
        lat = min_lat - pad_lat
        while lat <= max_lat + pad_lat:
            lon = min_lon - pad_lon
            while lon <= max_lon + pad_lon:
                if _near_route((lon, lat), buckets, corridor_mi):
                    points.append((round(lon, 3), round(lat, 3)))
                lon += dlon
            lat += dlat

        if len(points) <= target * 1.3:
            return points, spacing
        spacing *= math.sqrt(len(points) / target)

    return points, spacing


def _intensity(wx, level):
    """
    0..1 value for the heatmap colour. The level alone gives hard steps
    between bands; the continuous score blends inside each band so the
    map shades smoothly, but it never shows less than the actual level.
    """
    score = continuous_score(wx["wind_mph"], wx["rain_in_hr"], wx["snow_in_hr"], level)
    return round(score / 4, 2)


def heatmap(lines, depart_ts, load_lb):
    points, spacing = build_grid(lines)
    start = int(depart_ts // 3600 * 3600)
    end = start + HOURS * 3600
    series = weather.get_series(points, start, end)

    levels, intensity = [], []
    for h in range(HOURS + 1):
        ts = start + h * 3600
        lv_row, in_row = [], []
        for lon, lat in points:
            wx = weather.at(weather.lookup(series, lon, lat), ts)
            if not wx["in_forecast"]:
                lv_row.append(-1)
                in_row.append(0)
                continue
            level = assess(wx["wind_mph"], wx["rain_in_hr"], wx["snow_in_hr"], load_lb).level
            lv_row.append(int(level))
            in_row.append(_intensity(wx, level))
        levels.append(lv_row)
        intensity.append(in_row)

    return {
        "start_ts": start,
        "hours": HOURS,
        "spacing_mi": round(spacing, 1),
        "points": [[lon, lat] for lon, lat in points],
        "levels": levels,
        "intensity": intensity,
        "level_names": [lvl.key for lvl in Risk],
    }

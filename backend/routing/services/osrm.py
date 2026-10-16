"""
OSRM client. Defaults to the public demo server, which is fine for a demo
but rate limited. Point OSRM_URL at your own instance for anything real.

The public server only has a car profile, so travel times get a truck
speed cap applied later in the planner.
"""
import logging

import requests
from django.conf import settings

from ..geo import cumulative_miles, offset_point, overlap_ratio

log = logging.getLogger(__name__)


class RoutingError(Exception):
    pass


def _fetch(points, alternatives=0):
    coords = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in points)
    params = {
        "overview": "full",
        "geometries": "geojson",
        "annotations": "duration",
        "steps": "false",
    }
    if alternatives:
        params["alternatives"] = alternatives
    url = f"{settings.OSRM_URL.rstrip('/')}/route/v1/driving/{coords}"
    try:
        resp = requests.get(url, params=params, timeout=settings.HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise RoutingError(f"Routing service unreachable: {exc}") from exc

    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code != 200 or data.get("code") != "Ok":
        raise RoutingError(data.get("message") or f"Routing failed ({resp.status_code})")
    return [_normalize(r) for r in data["routes"]]


def _normalize(route):
    coords = [tuple(c) for c in route["geometry"]["coordinates"]]
    seg_durations = []
    for leg in route["legs"]:
        seg_durations.extend(leg.get("annotation", {}).get("duration", []))

    # Per-segment durations normally line up 1:1 with the geometry. If they
    # don't (multi-leg quirks), spread the total time by distance instead.
    if len(seg_durations) != len(coords) - 1:
        cum = cumulative_miles(coords)
        total = cum[-1] or 1
        seg_durations = [
            route["duration"] * (cum[i + 1] - cum[i]) / total for i in range(len(coords) - 1)
        ]

    return {
        "coords": coords,
        "segment_durations": seg_durations,
        "duration_s": route["duration"],
        "distance_m": route["distance"],
    }


def _is_distinct(candidate, existing):
    return all(overlap_ratio(candidate["coords"], r["coords"]) < 0.8 for r in existing)


def get_routes(origin, destination, wanted=3):
    """
    Up to `wanted` meaningfully different routes. OSRM's own alternatives
    come first; if it returns fewer, I force detours through points pushed
    off to either side of the straight line and keep the ones that don't
    just duplicate an existing route.
    """
    routes = _fetch([origin, destination], alternatives=wanted)[:wanted]
    if len(routes) >= wanted:
        return routes

    straight = cumulative_miles([origin, destination])[-1]
    nudges = [
        (0.5, 0.12), (0.5, -0.12),
        (0.5, 0.25), (0.5, -0.25),
        (0.33, 0.18), (0.66, -0.18),
    ]
    for along, frac in nudges:
        if len(routes) >= wanted:
            break
        via = offset_point(origin, destination, along, straight * frac)
        try:
            candidate = _fetch([origin, via, destination])[0]
        except RoutingError as exc:
            log.info("detour via %s failed: %s", via, exc)
            continue
        # throw away detours that are absurdly longer than the fastest route
        if candidate["duration_s"] > routes[0]["duration_s"] * 1.6:
            continue
        if _is_distinct(candidate, routes):
            routes.append(candidate)

    return routes

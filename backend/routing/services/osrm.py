"""
OSRM client. Defaults to the public demo server, which is fine for a demo
but rate limited (roughly one request a second). Point OSRM_URL at your own
instance for anything real.

The public server only has a car profile, so travel times get a truck
speed cap applied later in the planner.
"""
import logging
import threading
import time

import requests
from django.conf import settings
from django.core.cache import cache

from ..geo import cumulative_miles, offset_point, overlap_ratio

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
ROUTE_CACHE_SECONDS = 60 * 60

_lock = threading.Lock()
_last_call = 0.0


class RoutingError(Exception):
    pass


class RateLimited(RoutingError):
    pass


def _wait_turn():
    """Space requests out so a search with detours doesn't trip the rate limit."""
    global _last_call
    with _lock:
        gap = settings.OSRM_MIN_INTERVAL - (time.monotonic() - _last_call)
        if gap > 0:
            time.sleep(gap)
        _last_call = time.monotonic()


def _request(points, alternatives):
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

    _wait_turn()
    try:
        resp = requests.get(url, params=params, timeout=settings.HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise RoutingError(f"Routing service unreachable: {exc}") from exc

    try:
        data = resp.json()
    except ValueError:
        data = {}

    message = data.get("message") or ""
    if resp.status_code == 429 or "overloaded" in message.lower() or data.get("code") == "TooManyRequests":
        raise RateLimited("The routing service is busy right now. Try again in a few seconds.")
    if resp.status_code != 200 or data.get("code") != "Ok":
        raise RoutingError(message or f"Routing failed ({resp.status_code})")
    return [_normalize(r) for r in data["routes"]]


def _fetch(points, alternatives=0):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _request(points, alternatives)
        except RateLimited:
            if attempt == MAX_ATTEMPTS:
                raise
            log.info("osrm rate limited, retry %d", attempt)
            time.sleep(1.5 * attempt)


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

    Routes don't depend on departure time or load, so they're cached and a
    re-run with different settings doesn't hit OSRM at all.
    """
    key = f"routes:{origin[0]:.4f},{origin[1]:.4f}:{destination[0]:.4f},{destination[1]:.4f}:{wanted}"
    cached = cache.get(key)
    if cached:
        return cached

    routes = _fetch([origin, destination], alternatives=wanted)[:wanted]

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
        except RateLimited:
            # keep what we have rather than failing the whole search
            log.info("osrm still rate limited, returning %d routes", len(routes))
            break
        except RoutingError as exc:
            log.info("detour via %s failed: %s", via, exc)
            continue
        # throw away detours that are absurdly longer than the fastest route
        if candidate["duration_s"] > routes[0]["duration_s"] * 1.6:
            continue
        if _is_distinct(candidate, routes):
            routes.append(candidate)

    cache.set(key, routes, ROUTE_CACHE_SECONDS)
    return routes

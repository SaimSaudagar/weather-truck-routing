import json
import logging
import time
from datetime import datetime, timezone

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import corridor
from .planner import plan_trip
from .services import geocoder
from .services.geocoder import GeocodeError
from .services.osrm import RoutingError
from .services.weather import WeatherError

log = logging.getLogger(__name__)

INTERVALS = (10, 25, 50)
MAX_LOAD_LB = 80_000  # federal gross weight limit without a permit
MAX_DAYS_AHEAD = 7


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _parse_departure(value):
    if not value:
        return time.time()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Departure time isn't a valid date")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ts = dt.timestamp()
    now = time.time()
    if ts < now - 3600:
        raise ValueError("Departure time is in the past")
    if ts > now + MAX_DAYS_AHEAD * 86400:
        raise ValueError(f"Forecasts only go about {MAX_DAYS_AHEAD} days out")
    return ts


@require_GET
def geocode(request):
    try:
        return JsonResponse({"results": geocoder.search(request.GET.get("q", ""))})
    except GeocodeError as exc:
        return _error(str(exc), 502)


@csrf_exempt
@require_POST
def plan(request):
    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return _error("Request body must be JSON")

    try:
        load_lb = float(body.get("load_lb", 0))
    except (TypeError, ValueError):
        return _error("Load weight must be a number")
    if not 0 < load_lb <= MAX_LOAD_LB:
        return _error(f"Load weight must be between 1 and {MAX_LOAD_LB:,} lb")

    try:
        interval = int(body.get("interval_mi", 25))
    except (TypeError, ValueError):
        interval = None
    if interval not in INTERVALS:
        return _error("Sampling interval must be 10, 25 or 50 miles")

    try:
        depart_ts = _parse_departure(body.get("departure"))
    except ValueError as exc:
        return _error(str(exc))

    if not body.get("origin") or not body.get("destination"):
        return _error("Origin and destination are required")

    try:
        origin = geocoder.resolve(body["origin"])
        destination = geocoder.resolve(body["destination"])
        result = plan_trip(
            origin, destination, depart_ts, load_lb, interval,
            use_hos=bool(body.get("hos", True)),
        )
    except GeocodeError as exc:
        return _error(str(exc), 422)
    except (RoutingError, WeatherError) as exc:
        log.warning("plan failed: %s", exc)
        return _error(str(exc), 502)

    return JsonResponse(result)


@require_GET
def heatmap(request, plan_id):
    stored = cache.get(f"plan:{plan_id}")
    if not stored:
        return _error("Plan expired, run the route again", 404)

    cache_key = f"heat:{plan_id}"
    data = cache.get(cache_key)
    if data is None:
        try:
            data = corridor.heatmap(stored["lines"], stored["depart_ts"], stored["load_lb"])
        except WeatherError as exc:
            return _error(str(exc), 502)
        cache.set(cache_key, data, 30 * 60)
    return JsonResponse(data)


@require_GET
def health(request):
    return JsonResponse({"ok": True})

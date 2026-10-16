"""
Hourly forecasts from Open-Meteo.

Locations are batched (the API takes comma separated lat/lon lists) and
each point's series is cached, so the heatmap and the route checkpoints
share fetches and re-running a plan a few minutes later is instant.
"""
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)

HOUR = 3600
DAY = 86400
BATCH_SIZE = 50
HOURLY_VARS = ["wind_speed_10m", "wind_gusts_10m", "rain", "showers", "snowfall", "weather_code"]


class WeatherError(Exception):
    pass


def _round_point(lon, lat):
    # 0.1 degree (~5-7 mi) is about the resolution of the forecast models
    # outside HRRR, and it lets overlapping routes share lookups. Open-Meteo
    # bills every location in a batched call separately, so this matters.
    return (round(lon, 1), round(lat, 1))


def _window(start_ts, end_ts):
    """Snap to whole UTC days so overlapping requests hit the same cache entry."""
    return int(start_ts // DAY * DAY), int(math.ceil((end_ts + HOUR) / DAY) * DAY)


def _iso_hour(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:00")


def _key(point, window):
    return f"wx:{point[0]:.1f}:{point[1]:.1f}:{window[0]}:{window[1]}"


def _fetch_batch(points, window):
    params = {
        "latitude": ",".join(f"{lat:.1f}" for _, lat in points),
        "longitude": ",".join(f"{lon:.1f}" for lon, _ in points),
        "hourly": ",".join(HOURLY_VARS),
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",  # also switches snowfall from cm to inches
        "timeformat": "unixtime",
        "timezone": "GMT",
        "start_hour": _iso_hour(window[0]),
        "end_hour": _iso_hour(window[1] - HOUR),
    }
    if settings.OPEN_METEO_API_KEY:
        params["apikey"] = settings.OPEN_METEO_API_KEY
    try:
        resp = requests.get(settings.OPEN_METEO_URL, params=params, timeout=settings.HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise WeatherError(f"Weather service unreachable: {exc}") from exc
    if resp.status_code != 200:
        try:
            reason = resp.json().get("reason")
        except ValueError:
            reason = None
        raise WeatherError(reason or f"Weather request failed ({resp.status_code})")

    payload = resp.json()
    if isinstance(payload, dict):
        payload = [payload]

    out = {}
    for point, item in zip(points, payload):
        hourly = item["hourly"]
        series = {"t0": hourly["time"][0], "n": len(hourly["time"])}
        for var in HOURLY_VARS:
            series[var] = [v if v is not None else 0 for v in hourly[var]]
        out[point] = series
    return out


def get_series(points, start_ts, end_ts):
    """
    Returns {rounded_point: series} for every requested (lon, lat).
    Callers look values up with `at()`.
    """
    window = _window(start_ts, end_ts)
    rounded = list(dict.fromkeys(_round_point(*p) for p in points))

    found = cache.get_many([_key(p, window) for p in rounded])
    result = {}
    missing = []
    for p in rounded:
        hit = found.get(_key(p, window))
        if hit:
            result[p] = hit
        else:
            missing.append(p)

    if missing:
        batches = [missing[i:i + BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            for fetched in pool.map(lambda b: _fetch_batch(b, window), batches):
                result.update(fetched)
                cache.set_many(
                    {_key(p, window): s for p, s in fetched.items()},
                    settings.WEATHER_CACHE_SECONDS,
                )
        log.info("weather: %d cached, %d fetched", len(rounded) - len(missing), len(missing))

    return result


def lookup(series_by_point, lon, lat):
    return series_by_point[_round_point(lon, lat)]


def at(series, ts):
    """
    Conditions at unix time `ts`.

    Wind is an instantaneous value, so take the nearest hour. Rain and snow
    are sums over the *preceding* hour, so a truck passing at 14:20 is in
    the 14:00–15:00 bucket, which Open-Meteo labels 15:00.
    """
    n = series["n"]
    offset = (ts - series["t0"]) / HOUR
    wind_i = min(max(round(offset), 0), n - 1)
    precip_i = min(max(math.ceil(offset), 0), n - 1)
    in_range = -0.5 <= offset <= n - 0.5

    rain = series["rain"][precip_i] + series["showers"][precip_i]
    return {
        "time": series["t0"] + wind_i * HOUR,
        "wind_mph": round(series["wind_speed_10m"][wind_i], 1),
        "gust_mph": round(series["wind_gusts_10m"][wind_i], 1),
        "rain_in_hr": round(rain, 3),
        "snow_in_hr": round(series["snowfall"][precip_i], 3),
        "weather_code": int(series["weather_code"][wind_i]),
        "in_forecast": in_range,
    }

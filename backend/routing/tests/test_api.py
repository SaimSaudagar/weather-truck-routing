"""
End to end through the Django views with the three external services faked.

Three straight-ish routes from Dallas to Chicago; the weather fake puts a
strong wind band over the western half of the map so the western route
should lose.
"""
import json
import time
from datetime import datetime, timezone
from unittest import mock

import pytest
from django.core.cache import cache

ORIGIN = {"label": "Dallas, TX", "lon": -96.797, "lat": 32.777}
DEST = {"label": "Chicago, IL", "lon": -87.623, "lat": 41.881}


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def _line(bend_lon, steps=60):
    """Dallas -> (bend) -> Chicago as a dense polyline."""
    pts = []
    mid = ((ORIGIN["lon"] + DEST["lon"]) / 2 + bend_lon, (ORIGIN["lat"] + DEST["lat"]) / 2)
    for a, b in ((ORIGIN, mid), (mid, DEST)):
        a = (a["lon"], a["lat"]) if isinstance(a, dict) else a
        b = (b["lon"], b["lat"]) if isinstance(b, dict) else b
        for i in range(steps):
            t = i / steps
            pts.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
    pts.append([DEST["lon"], DEST["lat"]])
    return pts


def _osrm_route(bend, hours):
    coords = _line(bend)
    n = len(coords) - 1
    return {
        "geometry": {"coordinates": coords},
        "legs": [{"annotation": {"duration": [hours * 3600 / n] * n}}],
        "duration": hours * 3600,
        "distance": 1_500_000,
    }


def fake_get(url, params=None, **kwargs):
    if "route/v1" in url:
        return FakeResponse({
            "code": "Ok",
            "routes": [_osrm_route(-3.0, 13), _osrm_route(0, 14), _osrm_route(3.0, 15)],
        })
    if "open-meteo" in url:
        lats = params["latitude"].split(",")
        lons = params["longitude"].split(",")
        start = int(datetime.strptime(params["start_hour"], "%Y-%m-%dT%H:%M")
                    .replace(tzinfo=timezone.utc).timestamp())
        end = int(datetime.strptime(params["end_hour"], "%Y-%m-%dT%H:%M")
                  .replace(tzinfo=timezone.utc).timestamp())
        n = (end - start) // 3600 + 1
        out = []
        for lat, lon in zip(lats, lons):
            windy = float(lon) < -93.5
            out.append({"hourly": {
                "time": [start + i * 3600 for i in range(n)],
                "wind_speed_10m": [48.0 if windy else 12.0] * n,
                "wind_gusts_10m": [60.0 if windy else 18.0] * n,
                "rain": [0.0] * n,
                "showers": [0.0] * n,
                "snowfall": [0.0] * n,
                "weather_code": [3] * n,
            }})
        return FakeResponse(out if len(out) > 1 else out[0])
    if "photon" in url:
        return FakeResponse({"features": [{
            "geometry": {"coordinates": [-87.623, 41.881]},
            "properties": {"name": "Chicago", "state": "Illinois", "country": "United States"},
        }]})
    raise AssertionError(f"unexpected url {url}")


@pytest.fixture(autouse=True)
def fake_services(settings):
    settings.OSRM_MIN_INTERVAL = 0
    cache.clear()
    with mock.patch("requests.get", side_effect=fake_get):
        yield


def _post(client, **overrides):
    body = {
        "origin": ORIGIN,
        "destination": DEST,
        "departure": datetime.fromtimestamp(time.time() + 3600, tz=timezone.utc).isoformat(),
        "load_lb": 35_000,
        "interval_mi": 25,
    } | overrides
    return client.post("/api/plan", data=json.dumps(body), content_type="application/json")


def test_plan_returns_three_ranked_routes(client):
    resp = _post(client)
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["routes"]) == 3
    assert [r["rank"] for r in data["routes"]] == [1, 2, 3]
    # the western route runs through 48 mph wind with 35k lb -> No Travel
    assert data["routes"][-1]["id"] == "a"
    assert data["routes"][-1]["risk_miles"]["no_travel"] > 0
    assert data["recommendation"]["route_id"] == data["routes"][0]["id"]


def test_checkpoints_follow_interval_and_eta_increases(client):
    data = _post(client, interval_mi=50).json()
    route = data["routes"][0]
    miles = [cp["mile"] for cp in route["checkpoints"]]
    assert miles[0] == 0
    gaps = [b - a for a, b in zip(miles, miles[1:])]
    assert all(g == pytest.approx(50, abs=0.1) for g in gaps[:-1])
    # the last gap can stretch a little when the final mark is merged into the destination
    assert gaps[-1] <= 60
    etas = [cp["eta"] for cp in route["checkpoints"]]
    assert etas == sorted(etas)
    # every mile is attributed to exactly one checkpoint
    covered = sum(cp["covers_mi"] for cp in route["checkpoints"])
    assert covered == pytest.approx(route["distance_mi"], abs=0.5)


def test_lighter_load_changes_the_outcome(client):
    heavy = _post(client, load_lb=35_000).json()
    light = _post(client, load_lb=20_000).json()
    west_heavy = next(r for r in heavy["routes"] if r["id"] == "a")
    west_light = next(r for r in light["routes"] if r["id"] == "a")
    assert west_heavy["risk_miles"]["no_travel"] > 0
    assert west_light["risk_miles"]["no_travel"] == 0
    assert west_light["risk_miles"]["severe"] > 0


def test_heatmap_frames(client):
    plan_id = _post(client).json()["id"]
    resp = client.get(f"/api/plan/{plan_id}/heatmap")
    assert resp.status_code == 200
    heat = resp.json()
    assert len(heat["levels"]) == 49
    assert all(len(row) == len(heat["points"]) for row in heat["levels"])
    assert 0 < len(heat["points"]) <= 500


def test_geocode_text_destination(client):
    resp = _post(client, destination="Chicago")
    assert resp.status_code == 200
    assert resp.json()["destination"]["label"].startswith("Chicago")


@pytest.mark.parametrize("override,message", [
    ({"load_lb": 0}, "Load weight"),
    ({"load_lb": 120_000}, "Load weight"),
    ({"interval_mi": 30}, "interval"),
    ({"departure": "2001-01-01T00:00:00Z"}, "past"),
])
def test_validation(client, override, message):
    resp = _post(client, **override)
    assert resp.status_code == 400
    assert message in resp.json()["error"]


def test_rate_limited_router_is_retried(client):
    calls = {"n": 0}

    def flaky(url, params=None, **kwargs):
        if "route/v1" in url:
            calls["n"] += 1
            if calls["n"] == 1:
                return FakeResponse({"message": "The service is overloaded"}, status=429)
        return fake_get(url, params, **kwargs)

    with mock.patch("routing.services.osrm.time.sleep"), mock.patch("requests.get", side_effect=flaky):
        resp = _post(client)
    assert resp.status_code == 200
    assert calls["n"] == 2


def test_routes_are_cached_between_searches(client):
    with mock.patch("requests.get", side_effect=fake_get) as get:
        _post(client, load_lb=20_000)
        _post(client, load_lb=40_000)
    route_calls = [c for c in get.call_args_list if "route/v1" in c.args[0]]
    assert len(route_calls) == 1


def test_persistent_rate_limit_gives_friendly_error(client):
    def busy(url, params=None, **kwargs):
        if "route/v1" in url:
            return FakeResponse({"message": "The service is overloaded"}, status=429)
        return fake_get(url, params, **kwargs)

    with mock.patch("routing.services.osrm.time.sleep"), mock.patch("requests.get", side_effect=busy):
        resp = _post(client)
    assert resp.status_code == 502
    assert "busy" in resp.json()["error"]

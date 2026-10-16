# Weather-Aware Truck Routing

React + Django app that gives a truck driver three route options between two
places, checks the forecast at the time the truck will actually be at each
point along the way, and recommends the safest one.

**Live:** _add link_ · **Walkthrough:** _add Loom link_

## Running it locally

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py runserver
```

Frontend (Node 18+):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to Django on :8000, so there's
nothing to configure for local dev. No API keys are needed.

Tests: `cd backend && pytest`

## How it works

1. **Geocoding.** Photon (OSM data). The inputs autocomplete; if you type a place
   and don't pick a suggestion, the backend geocodes the text.
2. **Routes.** OSRM. I ask for alternatives first. OSRM often only finds one or two,
   so I force detours through points pushed off either side of the straight line
   between origin and destination. I keep a detour only if it overlaps less than
   80% with the routes I already have and isn't more than 60% slower than the
   fastest one.
3. **Checkpoints.** I walk each route's geometry and drop a point every 10, 25 or
   50 miles (user's choice), plus one at the destination.
4. **ETAs.** OSRM gives a duration for every segment of the line. The public server
   only has a car profile, so I cap each segment at 65 mph (configurable). With
   HOS on, I add a 30-minute break after 8 hours of driving and a 10-hour rest
   after 11. Without that, a 1,500-mile ETA is off by most of a day, which also
   means you'd be checking the wrong forecast hour.
5. **Weather.** Open-Meteo hourly forecast, all checkpoints from all three routes in
   batched requests. Wind is an instantaneous value, so I take the nearest hour.
   Rain and snow are totals for the *preceding* hour, so a truck passing at 14:20
   uses the 15:00 value (which covers 14:00–15:00). Rain is `rain + showers`.
   Snowfall comes back in inches because `precipitation_unit=inch` applies to it too.
6. **Risk.** Each checkpoint is scored on wind, rain and snow separately and takes
   the worst. Then the load rules apply (see below).
7. **Ranking.** See the recommendation section below.
8. **Heatmap.** A grid of points covers the area within 40 miles of any route.
   Spacing scales with trip length, so the grid stays around 250 points. The
   backend computes all 49 hourly frames (0–48h from departure) in one request.
   The frontend builds each frame's GeoJSON once, so moving the slider is just a
   `setData` on a MapLibre heatmap layer. The routes show up first and the
   heatmap loads behind them.

## Decisions on the rules

**Shared boundaries.** The table repeats boundary values (rain 0.25 sits in both
Moderate and High), so every band includes its lower bound: 35 mph is High,
0.25 in/hr is High. Rain and snow No Travel are written as `>1.00` and `>3.0`,
so exactly 1.00 in/hr of rain is still Severe.

**Wind speed.** I use sustained 10 m wind for scoring. Gusts appear in the
checkpoint popup but don't count; the brief doesn't mention gusts and they would
dominate everything.

**Load rules.** These run after the weather level and can only raise it:

| Wind | Load | Result |
|---|---|---|
| ≥55 mph | any | No Travel |
| 45–54 mph | >30,000 lb | No Travel |
| 35–44 mph | >40,000 lb | Severe |

Exactly 30,000 or 40,000 lb doesn't trigger the bump, because the rules say "greater than."

**Assigning miles.** Each checkpoint represents the stretch of road nearest to it:
from halfway back to the previous checkpoint to halfway forward to the next. So
with 25-mile sampling, a Severe checkpoint adds about 25 Severe miles.

**Unscored miles.** If an ETA falls past the forecast range, that stretch is shown
grey and counted as unscored. It isn't treated as Low.

## Recommendation

The routes are sorted by the following, in order:

1. No Travel miles. The brief doesn't list this, but a route through a No Travel
   zone can't be the safe pick no matter how fast it is.
2. Severe miles
3. High miles
4. Average risk, mileage-weighted on a 0 (Low) to 4 (No Travel) scale
5. Total trip time, including HOS stops

Miles are compared to the nearest mile and average risk to one decimal. Without
that rounding, a 0.01 difference in average risk would always beat an hour of
driving and travel time would never matter. The UI says which criterion decided
the pick, for example "fewer Severe miles than Route A (0 vs 42 mi)", and warns
when even the best route has Severe or No Travel conditions.

## Project layout

```
backend/
  config/            settings, urls
  routing/
    risk.py          thresholds + load rules
    geo.py           distances, sampling, interpolation
    hos.py           hours-of-service timing
    planner.py       routes → checkpoints → weather → summaries
    ranking.py       recommendation order + explanation
    corridor.py      heatmap grid and frames
    services/        OSRM, Photon, Open-Meteo clients
    views.py         /api/plan, /api/plan/<id>/heatmap, /api/geocode
    tests/
frontend/
  src/
    App.jsx
    components/      TripForm, PlaceInput, RouteCard, MapView, HeatmapControl
```

The backend has no database. Plans and forecasts live in Django's cache:
in-memory by default, or Redis if `REDIS_URL` is set.

## Deploying

- **API:** `render.yaml` sets up a Render web service from `backend/`. Set
  `CORS_ALLOWED_ORIGINS` to the frontend URL. It runs a single gunicorn worker
  with threads on purpose: with the in-memory cache, the heatmap request has to
  hit the same process that built the plan. Add Redis before adding workers.
- **Frontend:** Vercel or Netlify with `frontend/` as the root. Set `VITE_API_URL`
  to the API URL.

## Known limits

- The public OSRM server is a demo instance with car routing only. It has no
  truck restrictions (bridge heights, hazmat, weight limits). In production I'd
  switch to a truck-aware router (HERE, PC*MILER, or self-hosted Valhalla/ORS with
  an HGV profile); only `services/osrm.py` would change.
- Open-Meteo's free tier is rate limited, and it counts each location in a
  batched call separately. Points are rounded to 0.1° (about the resolution of
  most forecast models) and cached for 30 minutes, which keeps repeat runs cheap.
- The HOS model skips the 14-hour duty window and the 70-hour/8-day limit.
- The heatmap uses forecast hours counted from departure, not "now".

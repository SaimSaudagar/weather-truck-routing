import { useCallback, useMemo, useState } from 'react'
import { fetchHeatmap, planTrip } from './api'
import { defaultDeparture, LEVELS, LEVEL_LABEL } from './format'
import TripForm from './components/TripForm'
import RouteCard from './components/RouteCard'
import MapView from './components/MapView'
import HeatmapControl from './components/HeatmapControl'

// where the truck is at a given unix time, interpolated between checkpoint ETAs
function truckPosition(route, ts) {
  const cps = route.checkpoints
  const times = cps.map((cp) => Date.parse(cp.eta) / 1000)
  if (ts <= times[0]) return [cps[0].lon, cps[0].lat]
  for (let i = 1; i < cps.length; i++) {
    if (ts <= times[i]) {
      const t = (ts - times[i - 1]) / (times[i] - times[i - 1] || 1)
      return [
        cps[i - 1].lon + (cps[i].lon - cps[i - 1].lon) * t,
        cps[i - 1].lat + (cps[i].lat - cps[i - 1].lat) * t,
      ]
    }
  }
  return null // already arrived
}

export default function App() {
  const [form, setForm] = useState({
    origin: '',
    destination: '',
    departure: defaultDeparture(),
    load: 36000,
    interval: 25,
    hos: true,
  })
  const [plan, setPlan] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [heat, setHeat] = useState(null)
  const [heatLoading, setHeatLoading] = useState(false)
  const [heatVisible, setHeatVisible] = useState(true)
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [focus, setFocus] = useState(null)

  const submit = useCallback(async () => {
    setLoading(true)
    setError('')
    setPlaying(false)
    try {
      const result = await planTrip({
        origin: form.origin,
        destination: form.destination,
        departure: new Date(form.departure).toISOString(),
        load_lb: Number(form.load),
        interval_mi: form.interval,
        hos: form.hos,
      })
      setPlan(result)
      setSelected(result.recommendation.route_id)
      setFocus(null)
      setHour(0)
      setHeat(null)

      // routes are on screen already; the corridor grid loads in behind them
      setHeatLoading(true)
      fetchHeatmap(result.id)
        .then(setHeat)
        .catch((e) => setError(`Heatmap: ${e.message}`))
        .finally(() => setHeatLoading(false))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [form])

  // every frame is built once per heatmap, so moving the slider is just a setData
  const frames = useMemo(() => {
    if (!heat) return null
    return heat.intensity.map((row, h) => ({
      type: 'FeatureCollection',
      features: row.flatMap((w, i) =>
        heat.levels[h][i] < 0
          ? []
          : [{ type: 'Feature', properties: { w }, geometry: { type: 'Point', coordinates: heat.points[i] } }],
      ),
    }))
  }, [heat])

  const selectedRoute = plan?.routes.find((r) => r.id === selected)
  const truck = useMemo(() => {
    if (!heat || !selectedRoute) return null
    return truckPosition(selectedRoute, heat.start_ts + hour * 3600)
  }, [heat, selectedRoute, hour])

  const rec = plan?.recommendation
  const best = plan?.routes.find((r) => r.id === rec?.route_id)

  return (
    <div className="app">
      <aside className="panel">
        <header className="brand">
          <h1>Weather-Aware Truck Routing</h1>
          <p>Three routes, forecast at the truck's arrival time at every checkpoint.</p>
        </header>

        <TripForm form={form} setForm={setForm} onSubmit={submit} loading={loading} />

        {error && <div className="error">{error}</div>}

        {plan && (
          <>
            <section className="recommendation">
              <h2>Take {best.name}</h2>
              <ul>
                {rec.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {rec.warning && <p className="warning">{rec.warning}</p>}
              <p className="meta">
                Worst conditions on this route: {LEVEL_LABEL[LEVELS[best.max_level]]}
              </p>
            </section>

            <div className="routes">
              {plan.routes.map((r) => (
                <RouteCard
                  key={r.id}
                  route={r}
                  selected={r.id === selected}
                  onSelect={setSelected}
                  onFocusCheckpoint={setFocus}
                />
              ))}
            </div>
          </>
        )}

        <footer className="credits">
          Routing © OSRM · Forecasts © Open-Meteo · Places © Photon/OSM
        </footer>
      </aside>

      <main className="map-wrap">
        <MapView
          plan={plan}
          selectedId={selected}
          onSelect={setSelected}
          heat={heat}
          heatFrame={frames?.[hour]}
          heatVisible={heatVisible}
          focus={focus}
          truck={truck}
        />
        {!plan && !loading && (
          <div className="map-empty">Enter a trip to compare routes</div>
        )}
        {plan && (
          <HeatmapControl
            heat={heat}
            hour={hour}
            setHour={setHour}
            visible={heatVisible}
            setVisible={setHeatVisible}
            playing={playing}
            setPlaying={setPlaying}
            loading={heatLoading}
          />
        )}
      </main>
    </div>
  )
}

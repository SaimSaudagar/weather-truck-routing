import { LEVELS, LEVEL_COLOR, LEVEL_LABEL, clock, duration, miles } from '../format'

function stopsLabel(breaks, rests) {
  const parts = []
  if (rests) parts.push(`${rests} rest${rests > 1 ? 's' : ''}`)
  if (breaks) parts.push(`${breaks} break${breaks > 1 ? 's' : ''}`)
  return parts.length ? `incl. ${parts.join(', ')}` : 'trip time'
}

function RiskBar({ riskMiles, unscored, total }) {
  const parts = [...LEVELS.map((l) => [l, riskMiles[l]]), ['unknown', unscored]]
  return (
    <div className="risk-bar" aria-label="Miles by risk level">
      {parts
        .filter(([, mi]) => mi > 0)
        .map(([level, mi]) => (
          <span
            key={level}
            style={{ width: `${(mi / total) * 100}%`, background: LEVEL_COLOR[level] }}
            title={`${LEVEL_LABEL[level]}: ${miles(mi)}`}
          />
        ))}
    </div>
  )
}

function Checkpoints({ route, onFocus }) {
  return (
    <div className="checkpoints">
      <table>
        <thead>
          <tr>
            <th>Mile</th>
            <th>ETA</th>
            <th>Wind</th>
            <th>Rain</th>
            <th>Snow</th>
            <th>Risk</th>
          </tr>
        </thead>
        <tbody>
          {route.checkpoints.map((cp) => (
            <tr key={cp.index} onClick={() => onFocus(cp)}>
              <td>{Math.round(cp.mile)}</td>
              <td>{clock(cp.eta)}</td>
              <td>{Math.round(cp.weather.wind_mph)}</td>
              <td>{cp.weather.rain_in_hr.toFixed(2)}</td>
              <td>{cp.weather.snow_in_hr.toFixed(2)}</td>
              <td>
                <span className={`chip ${cp.risk.level}`}>{LEVEL_LABEL[cp.risk.level]}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">Wind mph · rain and snow in/hr · click a row to find it on the map</p>
    </div>
  )
}

export default function RouteCard({ route, selected, onSelect, onFocusCheckpoint }) {
  const rm = route.risk_miles
  const { breaks, rests } = route.hos_stops

  return (
    <article
      className={`route-card ${selected ? 'selected' : ''}`}
      onClick={() => !selected && onSelect(route.id)}
    >
      <header>
        <h3>
          {route.name}
          {route.recommended && <span className="badge">Recommended</span>}
        </h3>
        <span className="rank">#{route.rank}</span>
      </header>

      <div className="stats">
        <div>
          <strong>{miles(route.distance_mi)}</strong>
          <span>distance</span>
        </div>
        <div>
          <strong>{duration(route.trip_s)}</strong>
          <span>{stopsLabel(breaks, rests)}</span>
        </div>
        <div>
          <strong>{clock(route.arrival)}</strong>
          <span>arrival</span>
        </div>
      </div>

      <RiskBar riskMiles={rm} unscored={route.unscored_mi} total={route.distance_mi} />

      <dl className="risk-numbers">
        <div>
          <dt>Severe</dt>
          <dd>{miles(rm.severe)}</dd>
        </div>
        <div>
          <dt>High</dt>
          <dd>{miles(rm.high)}</dd>
        </div>
        <div>
          <dt>Avg risk</dt>
          <dd>{route.avg_risk.toFixed(2)} / 4</dd>
        </div>
        {rm.no_travel > 0 && (
          <div className="danger">
            <dt>No Travel</dt>
            <dd>{miles(rm.no_travel)}</dd>
          </div>
        )}
      </dl>

      {route.unscored_mi > 0 && (
        <p className="hint">{miles(route.unscored_mi)} beyond the forecast range, not scored.</p>
      )}

      {selected && <Checkpoints route={route} onFocus={onFocusCheckpoint} />}
    </article>
  )
}

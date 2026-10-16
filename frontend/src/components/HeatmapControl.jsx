import { useEffect } from 'react'
import { LEVELS, LEVEL_COLOR, LEVEL_LABEL, clock } from '../format'

export default function HeatmapControl({ heat, hour, setHour, visible, setVisible, playing, setPlaying, loading }) {
  // simple playback: one hour every 400ms, loops back to 0
  useEffect(() => {
    if (!playing || !heat) return
    const id = setInterval(() => setHour((h) => (h >= heat.hours ? 0 : h + 1)), 400)
    return () => clearInterval(id)
  }, [playing, heat, setHour])

  const time = heat ? (heat.start_ts + hour * 3600) * 1000 : null

  return (
    <div className="heat-control">
      <div className="heat-top">
        <label className="check">
          <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
          Weather heatmap
        </label>
        <span className="heat-time">
          {loading && 'Loading forecast grid…'}
          {heat && !loading && (
            <>
              <strong>+{hour}h</strong> · {clock(time)}
            </>
          )}
        </span>
      </div>

      <div className="heat-slider">
        <button
          type="button"
          className="play"
          disabled={!heat}
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <input
          type="range"
          min="0"
          max={heat?.hours ?? 48}
          step="1"
          value={hour}
          disabled={!heat}
          onChange={(e) => {
            setPlaying(false)
            setHour(Number(e.target.value))
          }}
        />
      </div>

      <div className="legend">
        {LEVELS.map((l) => (
          <span key={l}>
            <i style={{ background: LEVEL_COLOR[l] }} />
            {LEVEL_LABEL[l]}
          </span>
        ))}
      </div>
    </div>
  )
}

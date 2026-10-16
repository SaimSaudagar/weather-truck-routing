import PlaceInput from './PlaceInput'

const INTERVALS = [10, 25, 50]

export default function TripForm({ form, setForm, onSubmit, loading }) {
  const update = (key) => (value) => setForm((f) => ({ ...f, [key]: value }))

  const swap = () =>
    setForm((f) => ({ ...f, origin: f.destination, destination: f.origin }))

  return (
    <form
      className="trip-form"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }}
    >
      <div className="places">
        <PlaceInput
          label="From"
          value={form.origin}
          onChange={update('origin')}
          placeholder="Dallas, TX"
        />
        <button type="button" className="swap" onClick={swap} title="Swap origin and destination">
          ⇅
        </button>
        <PlaceInput
          label="To"
          value={form.destination}
          onChange={update('destination')}
          placeholder="Chicago, IL"
        />
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input
            id="departure"
            type="datetime-local"
            value={form.departure}
            onChange={(e) => update('departure')(e.target.value)}
            required
          />
        </div>
        <div className="field narrow">
          <label htmlFor="load">Load (lb)</label>
          <input
            id="load"
            type="number"
            min="1"
            max="80000"
            step="500"
            value={form.load}
            onChange={(e) => update('load')(e.target.value)}
            required
          />
        </div>
      </div>

      <div className="row align-end">
        <div className="field">
          <label>Weather every</label>
          <div className="segmented">
            {INTERVALS.map((n) => (
              <button
                type="button"
                key={n}
                className={form.interval === n ? 'on' : ''}
                onClick={() => update('interval')(n)}
              >
                {n} mi
              </button>
            ))}
          </div>
        </div>
        <label className="check" title="30 min break after 8h driving, 10h rest after 11h">
          <input
            type="checkbox"
            checked={form.hos}
            onChange={(e) => update('hos')(e.target.checked)}
          />
          HOS breaks
        </label>
      </div>

      <button className="primary" type="submit" disabled={loading}>
        {loading ? 'Checking routes…' : 'Find safest route'}
      </button>
    </form>
  )
}

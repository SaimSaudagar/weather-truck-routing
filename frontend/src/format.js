export const LEVELS = ['low', 'moderate', 'high', 'severe', 'no_travel']

export const LEVEL_LABEL = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
  unknown: 'No forecast',
}

export const LEVEL_COLOR = {
  low: '#2f9e5b',
  moderate: '#e0b100',
  high: '#ee7a1c',
  severe: '#d62839',
  no_travel: '#6b1fa8',
  unknown: '#9aa5ad',
}

export function duration(seconds) {
  const mins = Math.round(seconds / 60)
  const h = Math.floor(mins / 60)
  const m = mins % 60
  if (h >= 24) {
    const d = Math.floor(h / 24)
    return `${d}d ${h % 24}h ${m}m`
  }
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`
}

const timeFmt = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  hour: 'numeric',
  minute: '2-digit',
})

export function clock(value) {
  return timeFmt.format(typeof value === 'number' ? new Date(value) : new Date(value))
}

export function miles(n) {
  return `${Math.round(n).toLocaleString()} mi`
}

// value for <input type="datetime-local">, 30 minutes from now rounded to 15
export function defaultDeparture() {
  const d = new Date(Date.now() + 30 * 60 * 1000)
  d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15, 0, 0)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

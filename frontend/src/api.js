const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

async function request(path, options = {}) {
  const res = await fetch(`${BASE}/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  let body = null
  try {
    body = await res.json()
  } catch {
    // non-JSON error page from a proxy or similar
  }
  if (!res.ok) {
    throw new Error(body?.error || `Request failed (${res.status})`)
  }
  return body
}

export function searchPlaces(q, signal) {
  return request(`/geocode?q=${encodeURIComponent(q)}`, { signal }).then((d) => d.results)
}

export function planTrip(payload) {
  return request('/plan', { method: 'POST', body: JSON.stringify(payload) })
}

export function fetchHeatmap(planId) {
  return request(`/plan/${planId}/heatmap`)
}

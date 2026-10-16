import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { LEVEL_COLOR, LEVEL_LABEL, clock } from '../format'

const STYLE = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'
const EMPTY = { type: 'FeatureCollection', features: [] }

const levelColor = ['match', ['get', 'level'], ...Object.entries(LEVEL_COLOR).flat(), '#888']

function escape(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
}

function popupHtml(cp) {
  const w = cp.weather
  const reasons = cp.risk.reasons?.length
    ? `<ul>${cp.risk.reasons.map((r) => `<li>${escape(r)}</li>`).join('')}</ul>`
    : ''
  return `
    <div class="cp-popup">
      <div class="cp-head">
        <span class="chip ${cp.risk.level}">${LEVEL_LABEL[cp.risk.level]}</span>
        <span>Mile ${Math.round(cp.mile)}</span>
      </div>
      <div class="cp-eta">ETA ${clock(cp.eta)}</div>
      <table>
        <tr><td>Wind</td><td>${w.wind_mph} mph <small>(gusts ${w.gust_mph})</small></td></tr>
        <tr><td>Rain</td><td>${w.rain_in_hr.toFixed(2)} in/hr</td></tr>
        <tr><td>Snow</td><td>${w.snow_in_hr.toFixed(2)} in/hr</td></tr>
      </table>
      ${reasons}
    </div>`
}

function routeFeatures(plan, selectedId) {
  const features = []
  for (const r of plan.routes) {
    if (r.id === selectedId) {
      for (const seg of r.segments) {
        features.push({
          type: 'Feature',
          properties: { route: r.id, selected: true, level: seg.level },
          geometry: { type: 'LineString', coordinates: seg.coords },
        })
      }
    } else {
      features.push({
        type: 'Feature',
        properties: { route: r.id, selected: false, level: 'unknown' },
        geometry: { type: 'LineString', coordinates: r.geometry },
      })
    }
  }
  return { type: 'FeatureCollection', features }
}

function checkpointFeatures(route) {
  return {
    type: 'FeatureCollection',
    features: route.checkpoints.map((cp) => ({
      type: 'Feature',
      properties: { index: cp.index, level: cp.risk.level },
      geometry: { type: 'Point', coordinates: [cp.lon, cp.lat] },
    })),
  }
}

// heatmap kernel radius that roughly matches the grid spacing at every zoom
function heatRadius(heat) {
  if (!heat) return 20
  const lat = heat.points.reduce((s, p) => s + p[1], 0) / heat.points.length
  const metersPerPxZ0 = 156543.03 * Math.cos((lat * Math.PI) / 180)
  const r0 = (heat.spacing_mi * 1609.344 * 1.1) / metersPerPxZ0
  // radius doubles with each zoom level; stop growing at 200px, past that
  // the GPU cost climbs and the grid is too coarse to be worth zooming into
  const zCap = Math.max(1, Math.log2(200 / r0))
  return ['interpolate', ['exponential', 2], ['zoom'], 0, r0, zCap, 200, 22, 200]
}

export default function MapView({ plan, selectedId, onSelect, heatFrame, heat, heatVisible, focus, truck }) {
  const container = useRef(null)
  const mapRef = useRef(null)
  const popupRef = useRef(null)
  const planRef = useRef(plan)
  const selectedRef = useRef(selectedId)
  const [ready, setReady] = useState(false)

  planRef.current = plan
  selectedRef.current = selectedId

  // set up the map and all layers once
  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: [-96, 38],
      zoom: 3.6,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: '260px', offset: 10 })

    map.on('load', () => {
      // put the heatmap under the place labels so cities stay readable
      const firstSymbol = map.getStyle().layers.find((l) => l.type === 'symbol')?.id

      map.addSource('heat', { type: 'geojson', data: EMPTY })
      map.addLayer(
        {
          id: 'heat',
          type: 'heatmap',
          source: 'heat',
          paint: {
            'heatmap-weight': ['interpolate', ['linear'], ['get', 'w'], 0, 0.08, 0.25, 0.15, 0.5, 0.4, 0.75, 0.75, 1, 1],
            'heatmap-intensity': 1,
            'heatmap-radius': 20,
            'heatmap-opacity': 0.75,
            'heatmap-color': [
              'interpolate', ['linear'], ['heatmap-density'],
              0, 'rgba(0,0,0,0)',
              0.08, 'rgba(47,158,91,0.22)',
              0.3, 'rgba(224,177,0,0.55)',
              0.5, 'rgba(238,122,28,0.65)',
              0.75, 'rgba(214,40,57,0.75)',
              0.95, 'rgba(107,31,168,0.8)',
            ],
          },
        },
        firstSymbol,
      )

      map.addSource('routes', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'route-other',
        type: 'line',
        source: 'routes',
        filter: ['==', ['get', 'selected'], false],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#5b6b75', 'line-width': 4, 'line-opacity': 0.55 },
      })
      map.addLayer({
        id: 'route-casing',
        type: 'line',
        source: 'routes',
        filter: ['==', ['get', 'selected'], true],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': '#0b2a35', 'line-width': 9 },
      })
      map.addLayer({
        id: 'route-selected',
        type: 'line',
        source: 'routes',
        filter: ['==', ['get', 'selected'], true],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': levelColor, 'line-width': 5.5 },
      })

      map.addSource('checkpoints', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'checkpoints',
        type: 'circle',
        source: 'checkpoints',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 3.5, 9, 7],
          'circle-color': levelColor,
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 1.5,
        },
      })

      map.addSource('ends', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'ends',
        type: 'circle',
        source: 'ends',
        paint: {
          'circle-radius': 8,
          'circle-color': ['match', ['get', 'kind'], 'origin', '#0b3d4c', '#f2b134'],
          'circle-stroke-color': '#fff',
          'circle-stroke-width': 3,
        },
      })

      map.addSource('truck', { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: 'truck',
        type: 'circle',
        source: 'truck',
        paint: {
          'circle-radius': 9,
          'circle-color': '#ffffff',
          'circle-stroke-color': '#0b3d4c',
          'circle-stroke-width': 4,
        },
      })

      map.on('click', 'checkpoints', (e) => {
        const index = e.features[0].properties.index
        const route = planRef.current?.routes.find((r) => r.id === selectedRef.current)
        const cp = route?.checkpoints[index]
        if (cp) popupRef.current.setLngLat([cp.lon, cp.lat]).setHTML(popupHtml(cp)).addTo(map)
      })
      map.on('click', 'route-other', (e) => {
        if (map.queryRenderedFeatures(e.point, { layers: ['checkpoints'] }).length) return
        onSelect(e.features[0].properties.route)
      })
      for (const layer of ['checkpoints', 'route-other']) {
        map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
        map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
      }

      setReady(true)
    })

    return () => map.remove()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // new plan: draw endpoints and zoom to fit every route
  useEffect(() => {
    const map = mapRef.current
    if (!ready) return
    popupRef.current.remove()
    if (!plan) {
      map.getSource('ends').setData(EMPTY)
      return
    }
    map.getSource('ends').setData({
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', properties: { kind: 'origin' }, geometry: { type: 'Point', coordinates: [plan.origin.lon, plan.origin.lat] } },
        { type: 'Feature', properties: { kind: 'dest' }, geometry: { type: 'Point', coordinates: [plan.destination.lon, plan.destination.lat] } },
      ],
    })
    const bounds = new maplibregl.LngLatBounds()
    plan.routes.forEach((r) => r.geometry.forEach((c) => bounds.extend(c)))
    const narrow = window.innerWidth < 800
    map.fitBounds(bounds, {
      padding: narrow ? 40 : { top: 60, bottom: 160, left: 60, right: 60 },
      duration: 900,
    })
  }, [plan, ready])

  // selection changes only restyle the lines and swap checkpoints
  useEffect(() => {
    const map = mapRef.current
    if (!ready) return
    if (!plan) {
      map.getSource('routes').setData(EMPTY)
      map.getSource('checkpoints').setData(EMPTY)
      return
    }
    const route = plan.routes.find((r) => r.id === selectedId) || plan.routes[0]
    map.getSource('routes').setData(routeFeatures(plan, route.id))
    map.getSource('checkpoints').setData(checkpointFeatures(route))
    popupRef.current.remove()
  }, [plan, selectedId, ready])

  useEffect(() => {
    if (!ready) return
    mapRef.current.setPaintProperty('heat', 'heatmap-radius', heatRadius(heat))
  }, [heat, ready])

  useEffect(() => {
    if (!ready) return
    mapRef.current.getSource('heat').setData(heatVisible && heatFrame ? heatFrame : EMPTY)
  }, [heatFrame, heatVisible, ready])

  useEffect(() => {
    if (!ready) return
    mapRef.current.getSource('truck').setData(
      truck ? { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: truck } } : EMPTY,
    )
  }, [truck, ready])

  useEffect(() => {
    if (!ready || !focus) return
    const map = mapRef.current
    map.flyTo({ center: [focus.lon, focus.lat], zoom: Math.max(map.getZoom(), 8), duration: 800 })
    popupRef.current.setLngLat([focus.lon, focus.lat]).setHTML(popupHtml(focus)).addTo(map)
  }, [focus, ready])

  return <div className="map" ref={container} />
}

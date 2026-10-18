import type { FeatureCollection, LineString } from 'geojson'
import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl'
import { COLORS } from '../config/map'
import type { LineStringGeometry } from '../types'

export const BASELINE_SOURCE = 'route-baseline'
export const WALKLAH_SOURCE = 'route-walklah'

const EMPTY: FeatureCollection<LineString> = { type: 'FeatureCollection', features: [] }
const BASELINE_DOTS = '#5b6b63'

export function lineCollection(geometry: LineStringGeometry | null | undefined): FeatureCollection<LineString> {
  if (!geometry || geometry.coordinates.length < 2) return EMPTY
  return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry }] }
}

/** Adds the route sources/layers if missing (they vanish whenever the style is replaced). */
export function ensureRouteLayers(map: MapLibreMap): void {
  if (!map.getSource(BASELINE_SOURCE)) map.addSource(BASELINE_SOURCE, { type: 'geojson', data: EMPTY })
  if (!map.getSource(WALKLAH_SOURCE)) map.addSource(WALKLAH_SOURCE, { type: 'geojson', data: EMPTY })

  // Usual (baseline) path: dark dots on a white band, drawn underneath. The band keeps it
  // distinct from the base map's dashed footpaths.
  if (!map.getLayer('route-baseline-casing')) {
    map.addLayer({
      id: 'route-baseline-casing',
      type: 'line',
      source: BASELINE_SOURCE,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': 10, 'line-opacity': 0.9 },
    })
  }
  if (!map.getLayer('route-baseline-line')) {
    map.addLayer({
      id: 'route-baseline-line',
      type: 'line',
      source: BASELINE_SOURCE,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': BASELINE_DOTS, 'line-width': 6, 'line-dasharray': [0, 2] },
    })
  }
  // WalkLah route: dark casing, bright green line, white "footsteps" flowing on top.
  if (!map.getLayer('route-walklah-casing')) {
    map.addLayer({
      id: 'route-walklah-casing',
      type: 'line',
      source: WALKLAH_SOURCE,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': COLORS.forest, 'line-width': 11, 'line-opacity': 0.85 },
    })
  }
  if (!map.getLayer('route-walklah-line')) {
    map.addLayer({
      id: 'route-walklah-line',
      type: 'line',
      source: WALKLAH_SOURCE,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': COLORS.greenBright, 'line-width': 7 },
    })
  }
  if (!map.getLayer('route-walklah-flow')) {
    map.addLayer({
      id: 'route-walklah-flow',
      type: 'line',
      source: WALKLAH_SOURCE,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': 2.5, 'line-opacity': 0.85, 'line-dasharray': [0, 4, 3] },
    })
  }
}

export function setRouteData(map: MapLibreMap, sourceId: string, geometry: LineStringGeometry | null | undefined): void {
  const source = map.getSource(sourceId) as GeoJSONSource | undefined
  source?.setData(lineCollection(geometry))
}

/** Dims the route that isn't selected so the chosen one reads first. */
export function setRouteFocus(map: MapLibreMap, focus: 'baseline' | 'walklah'): void {
  const walklahOpacity = focus === 'walklah' ? 1 : 0.3
  if (map.getLayer('route-walklah-line')) {
    map.setPaintProperty('route-walklah-line', 'line-opacity', walklahOpacity)
    map.setPaintProperty('route-walklah-casing', 'line-opacity', focus === 'walklah' ? 0.85 : 0.25)
    map.setPaintProperty('route-walklah-flow', 'line-opacity', focus === 'walklah' ? 0.85 : 0)
  }
  if (map.getLayer('route-baseline-line')) {
    map.setPaintProperty('route-baseline-line', 'line-color', focus === 'baseline' ? COLORS.forest : BASELINE_DOTS)
    map.setPaintProperty('route-baseline-line', 'line-width', focus === 'baseline' ? 8 : 6)
  }
}

// Marching dash steps (line-dasharray is in line-width units).
const FLOW_STEPS: number[][] = [
  [0, 4, 3],
  [0.5, 4, 2.5],
  [1, 4, 2],
  [1.5, 4, 1.5],
  [2, 4, 1],
  [2.5, 4, 0.5],
  [3, 4, 0],
  [0, 0.5, 3, 3.5],
  [0, 1, 3, 3],
  [0, 1.5, 3, 2.5],
  [0, 2, 3, 2],
  [0, 2.5, 3, 1.5],
  [0, 3, 3, 1],
  [0, 3.5, 3, 0.5],
]

/** Animates the white footsteps along the WalkLah line. Returns a stop function. */
export function startRouteFlow(map: MapLibreMap): () => void {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return () => undefined
  let step = 0
  const timer = window.setInterval(() => {
    if (!map.getLayer('route-walklah-flow')) return
    step = (step + 1) % FLOW_STEPS.length
    map.setPaintProperty('route-walklah-flow', 'line-dasharray', FLOW_STEPS[step])
  }, 70)
  return () => window.clearInterval(timer)
}

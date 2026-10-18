import type { Feature, FeatureCollection, LineString, Polygon } from 'geojson'
import type { ExpressionSpecification, GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl'
import { COLORS } from '../config/map'
import type { LatLon, PlannedRoute, RouteMode } from '../types'

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

export const SELECTED_SEGMENTS_LAYER = 'route-selected-state'

/** Colour of a route segment: shade/sun by day, lighting after dark. */
export type SegmentState = 'shade' | 'sun' | 'lit' | 'unlit' | 'unknown'

export const SEGMENT_COLORS: Record<SegmentState, string> = {
  shade: COLORS.greenBright,
  sun: COLORS.sun,
  lit: COLORS.kuning,
  unlit: COLORS.red,
  unknown: COLORS.unknown,
}

const stateColor: ExpressionSpecification = [
  'match',
  ['get', 'state'],
  'shade', SEGMENT_COLORS.shade,
  'sun', SEGMENT_COLORS.sun,
  'lit', SEGMENT_COLORS.lit,
  'unlit', SEGMENT_COLORS.unlit,
  SEGMENT_COLORS.unknown,
]

export function segmentState(shade: number | null, lit: string, night: boolean): SegmentState {
  if (night) return lit === 'yes' ? 'lit' : lit === 'no' ? 'unlit' : 'unknown'
  if (shade === null) return 'unknown'
  return shade >= 0.5 ? 'shade' : 'sun'
}

function ensureSource(map: MapLibreMap, id: string) {
  if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: EMPTY })
}

function setData(map: MapLibreMap, id: string, data: FeatureCollection) {
  ;(map.getSource(id) as GeoJSONSource | undefined)?.setData(data)
}

/** Adds every overlay source/layer if missing (they vanish whenever the style is replaced). */
export function ensureOverlayLayers(map: MapLibreMap): void {
  for (const id of ['pilot-ring', 'routes-alt', 'route-selected', 'route-selected-segments', 'scenario-link']) {
    ensureSource(map, id)
  }
  const add = (layer: Parameters<MapLibreMap['addLayer']>[0]) => {
    if (!map.getLayer(layer.id)) map.addLayer(layer)
  }
  add({
    id: 'pilot-ring-fill',
    type: 'fill',
    source: 'pilot-ring',
    paint: { 'fill-color': COLORS.kuning, 'fill-opacity': 0.05 },
  })
  add({
    id: 'pilot-ring-line',
    type: 'line',
    source: 'pilot-ring',
    paint: { 'line-color': COLORS.kuningDeep, 'line-width': 2, 'line-dasharray': [3, 2], 'line-opacity': 0.8 },
  })
  // Other route options: the shortest (baseline) as dark dots on a white band, the rest as soft lines.
  add({
    id: 'routes-alt-band',
    type: 'line',
    source: 'routes-alt',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#ffffff', 'line-width': 9, 'line-opacity': 0.85 },
  })
  add({
    id: 'routes-alt-other',
    type: 'line',
    source: 'routes-alt',
    filter: ['!=', ['get', 'mode'], 'shortest'],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#9db3a8', 'line-width': 5 },
  })
  add({
    id: 'routes-alt-shortest',
    type: 'line',
    source: 'routes-alt',
    filter: ['==', ['get', 'mode'], 'shortest'],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': COLORS.baselineDots, 'line-width': 6, 'line-dasharray': [0, 2] },
  })
  add({
    id: 'route-selected-casing',
    type: 'line',
    source: 'route-selected',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': COLORS.forest, 'line-width': 12, 'line-opacity': 0.9 },
  })
  add({
    id: SELECTED_SEGMENTS_LAYER,
    type: 'line',
    source: 'route-selected-segments',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': stateColor, 'line-width': 7 },
  })
  add({
    id: 'route-selected-flow',
    type: 'line',
    source: 'route-selected',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#ffffff', 'line-width': 2.5, 'line-opacity': 0.85, 'line-dasharray': [0, 4, 3] },
  })
  add({
    id: 'scenario-link-line',
    type: 'line',
    source: 'scenario-link',
    layout: { 'line-cap': 'round' },
    paint: { 'line-color': COLORS.blue, 'line-width': 6, 'line-dasharray': [1.5, 1] },
  })
}

export interface RouteDisplay {
  routes: PlannedRoute[]
  selected: RouteMode
  night: boolean
}

export function setRouteDisplay(map: MapLibreMap, display: RouteDisplay | null): void {
  const selected = display?.routes.find((r) => r.mode === display.selected) ?? null
  const others = display ? display.routes.filter((r) => r !== selected) : []
  setData(map, 'routes-alt', {
    type: 'FeatureCollection',
    features: others.map((r) => ({ type: 'Feature', properties: { mode: r.mode }, geometry: r.geometry })),
  })
  setData(map, 'route-selected', {
    type: 'FeatureCollection',
    features: selected ? [{ type: 'Feature', properties: { mode: selected.mode }, geometry: selected.geometry }] : [],
  })
  const segments: Feature<LineString>[] = selected
    ? selected.segments.map((s) => ({
        type: 'Feature',
        properties: { id: s.id, state: segmentState(s.shade, s.lit, display!.night) },
        geometry: { type: 'LineString', coordinates: s.coordinates },
      }))
    : []
  setData(map, 'route-selected-segments', { type: 'FeatureCollection', features: segments })
}

/** Approximate circle polygon (fine at this scale). */
export function circlePolygon(center: LatLon, radiusM: number, steps = 72): Feature<Polygon> {
  const coords: [number, number][] = []
  const latRad = (center.latitude * Math.PI) / 180
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI
    const dLat = (radiusM * Math.cos(a)) / 111_320
    const dLon = (radiusM * Math.sin(a)) / (111_320 * Math.cos(latRad))
    coords.push([center.longitude + dLon, center.latitude + dLat])
  }
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [coords] } }
}

export function setPilotRing(map: MapLibreMap, center: LatLon | null, radiusM: number): void {
  setData(map, 'pilot-ring', {
    type: 'FeatureCollection',
    features: center ? [circlePolygon(center, radiusM)] : [],
  })
}

export function setScenarioLink(map: MapLibreMap, start: LatLon | null, end: LatLon | null): void {
  setData(map, 'scenario-link', {
    type: 'FeatureCollection',
    features:
      start && end
        ? [
            {
              type: 'Feature',
              properties: {},
              geometry: {
                type: 'LineString',
                coordinates: [
                  [start.longitude, start.latitude],
                  [end.longitude, end.latitude],
                ],
              },
            },
          ]
        : [],
  })
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

/** Animates white "footsteps" along the selected route. Returns a stop function. */
export function startRouteFlow(map: MapLibreMap): () => void {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return () => undefined
  let step = 0
  const timer = window.setInterval(() => {
    if (!map.getLayer('route-selected-flow')) return
    step = (step + 1) % FLOW_STEPS.length
    map.setPaintProperty('route-selected-flow', 'line-dasharray', FLOW_STEPS[step])
  }, 70)
  return () => window.clearInterval(timer)
}

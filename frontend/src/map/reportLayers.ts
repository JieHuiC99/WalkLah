import type { FeatureCollection, Point } from 'geojson'
import type { ExpressionSpecification, GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl'
import { STATUS_META } from '../config/status'
import type { Report } from '../types'

export const REPORTS_SOURCE = 'reports'
export const REPORTS_LAYER = 'reports-circle'

const EMPTY: FeatureCollection<Point> = { type: 'FeatureCollection', features: [] }

function reportCollection(reports: Report[]): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: reports.map((r) => ({
      type: 'Feature',
      id: r.id,
      properties: { id: r.id, status: r.status },
      geometry: { type: 'Point', coordinates: [r.longitude, r.latitude] },
    })),
  }
}

const statusColor: ExpressionSpecification = [
  'match',
  ['get', 'status'],
  'pending',
  STATUS_META.pending.color,
  'verified_active',
  STATUS_META.verified_active.color,
  'verified_cleared',
  STATUS_META.verified_cleared.color,
  STATUS_META.stale.color,
]

export function ensureReportLayers(map: MapLibreMap): void {
  if (!map.getSource(REPORTS_SOURCE)) map.addSource(REPORTS_SOURCE, { type: 'geojson', data: EMPTY })
  // Pulsing ring under active obstacles (animated by startReportPulse).
  if (!map.getLayer('reports-pulse')) {
    map.addLayer({
      id: 'reports-pulse',
      type: 'circle',
      source: REPORTS_SOURCE,
      filter: ['==', ['get', 'status'], 'verified_active'],
      paint: { 'circle-color': '#e5484d', 'circle-radius': 12, 'circle-opacity': 0.35 },
    })
  }
  if (!map.getLayer(REPORTS_LAYER)) {
    map.addLayer({
      id: REPORTS_LAYER,
      type: 'circle',
      source: REPORTS_SOURCE,
      paint: {
        'circle-color': statusColor,
        'circle-radius': ['case', ['==', ['get', 'status'], 'verified_active'], 11, 9],
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 3,
      },
    })
  }
}

export function setReportData(map: MapLibreMap, reports: Report[]): void {
  const source = map.getSource(REPORTS_SOURCE) as GeoJSONSource | undefined
  source?.setData(reportCollection(reports))
}

/** Grows and fades the ring under active obstacles. Returns a stop function. */
export function startReportPulse(map: MapLibreMap): () => void {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return () => undefined
  let frame = 0
  const timer = window.setInterval(() => {
    if (!map.getLayer('reports-pulse')) return
    frame = (frame + 1) % 30
    const t = frame / 30
    map.setPaintProperty('reports-pulse', 'circle-radius', 12 + t * 18)
    map.setPaintProperty('reports-pulse', 'circle-opacity', 0.45 * (1 - t))
  }, 60)
  return () => window.clearInterval(timer)
}

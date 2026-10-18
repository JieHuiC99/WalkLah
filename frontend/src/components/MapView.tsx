import * as maplibregl from 'maplibre-gl'
import type { Map as MapLibreMap, PaddingOptions } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef, useState } from 'react'
import { categoryLabel } from '../config/categories'
import { MAP_CENTER, MAP_STYLE_URL, MAP_ZOOM, MAX_BOUNDS } from '../config/map'
import { STATUS_META } from '../config/status'
import { applyWalkLahPalette, FALLBACK_STYLE } from '../map/palette'
import { ensureReportLayers, REPORTS_LAYER, setReportData, startReportPulse } from '../map/reportLayers'
import {
  BASELINE_SOURCE,
  ensureRouteLayers,
  setRouteData,
  setRouteFocus,
  startRouteFlow,
  WALKLAH_SOURCE,
} from '../map/routeLayers'
import { reportPopupContent } from '../map/reportPopup'
import type { Destination, LineStringGeometry, Report } from '../types'
import { Icon } from './icons'

const STYLE_TIMEOUT_MS = 10_000

// MapLibre finds its worker relative to its own module URL, which breaks once Vite pre-bundles
// the library, so point it at the (self-contained) worker file explicitly.
maplibregl.setWorkerUrl(workerUrl)

export interface LatLon {
  latitude: number
  longitude: number
}

export interface FlyTarget extends LatLon {
  key: number
}

interface Props {
  destinations: Destination[]
  from: string | null
  to: string | null
  baseline: LineStringGeometry | null
  walklah: LineStringGeometry | null
  focus: 'baseline' | 'walklah'
  /** Changes whenever the camera should frame the current routes. */
  fitKey: string | null
  reports: Report[]
  /** Report placement mode: map clicks place (and dragging moves) the draft pin. */
  placing: boolean
  draft: LatLon | null
  onPlace: (point: LatLon) => void
  flyTarget: FlyTarget | null
  onOpenSurvey: () => void
}

/** Keeps routes clear of the side panel (desktop) or bottom sheet (phone). */
function cameraPadding(): PaddingOptions {
  const phone = window.innerWidth < 768
  if (phone) {
    return { top: 90, right: 70, bottom: Math.round(window.innerHeight * 0.64) + 24, left: 40 }
  }
  const panel = document.querySelector('.panel')?.getBoundingClientRect()
  return { top: 70, right: 90, bottom: 70, left: (panel?.right ?? 416) + 60 }
}

export function MapView(props: Props) {
  const { destinations, from, to, baseline, walklah, focus, fitKey, reports, placing, draft, onPlace, flyTarget, onOpenSurvey } =
    props
  const containerRef = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<MapLibreMap | null>(null)
  // Bumped each time a style finishes loading, so overlay data is re-applied after a style swap.
  const [styleVersion, setStyleVersion] = useState(0)
  const [baseMapFailed, setBaseMapFailed] = useState(false)

  // Latest values for map event handlers that are bound once.
  const live = useRef({ placing, onPlace, reports })
  useEffect(() => {
    live.current = { placing, onPlace, reports }
  })

  // Create the map once. StrictMode mounts twice in development, so cleanup must remove it.
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const instance = new maplibregl.Map({
      container,
      style: MAP_STYLE_URL,
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      minZoom: 13,
      maxZoom: 19,
      maxBounds: MAX_BOUNDS,
      attributionControl: false,
      dragRotate: false,
      pitchWithRotate: false,
    })
    instance.touchZoomRotate.disableRotation()
    instance.addControl(
      new maplibregl.AttributionControl({ compact: false, customAttribution: '© OpenStreetMap contributors' }),
      'bottom-right',
    )

    let styleLoaded = false
    let usingFallback = false
    const switchToFallback = () => {
      if (styleLoaded || usingFallback) return
      usingFallback = true
      setBaseMapFailed(true)
      instance.setStyle(FALLBACK_STYLE)
    }
    const timer = window.setTimeout(switchToFallback, STYLE_TIMEOUT_MS)

    instance.on('style.load', () => {
      if (!usingFallback) {
        styleLoaded = true
        applyWalkLahPalette(instance)
      }
      window.clearTimeout(timer)
      ensureRouteLayers(instance)
      ensureReportLayers(instance)
      setStyleVersion((v) => v + 1)
    })
    // Only a failure before the style has loaded triggers the fallback; later tile errors are ignored.
    instance.on('error', switchToFallback)
    instance.once('load', () => setMap(instance))

    // Clicking a report opens its details; otherwise, in placement mode, the click places the pin.
    let popup: maplibregl.Popup | null = null
    instance.on('click', (event) => {
      const hit = instance.getLayer(REPORTS_LAYER)
        ? instance.queryRenderedFeatures(event.point, { layers: [REPORTS_LAYER] })[0]
        : undefined
      const report = hit && live.current.reports.find((r) => r.id === hit.properties?.id)
      if (report) {
        popup?.remove()
        popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '260px' })
          .setLngLat([report.longitude, report.latitude])
          .setDOMContent(reportPopupContent(report))
          .addTo(instance)
        return
      }
      if (live.current.placing) {
        live.current.onPlace({ latitude: event.lngLat.lat, longitude: event.lngLat.lng })
      }
    })
    instance.on('mouseenter', REPORTS_LAYER, () => (instance.getCanvas().style.cursor = 'pointer'))
    instance.on('mouseleave', REPORTS_LAYER, () => (instance.getCanvas().style.cursor = ''))

    const stopFlow = startRouteFlow(instance)
    const stopPulse = startReportPulse(instance)

    return () => {
      window.clearTimeout(timer)
      stopFlow()
      stopPulse()
      popup?.remove()
      instance.remove()
      setMap(null)
    }
  }, [])

  // Route lines come only from /route geometry; no line is drawn when a route is missing.
  useEffect(() => {
    if (!map) return
    ensureRouteLayers(map)
    setRouteData(map, BASELINE_SOURCE, baseline)
    setRouteData(map, WALKLAH_SOURCE, walklah)
  }, [map, styleVersion, baseline, walklah])

  useEffect(() => {
    if (!map) return
    setRouteFocus(map, focus)
  }, [map, styleVersion, focus])

  useEffect(() => {
    if (!map) return
    ensureReportLayers(map)
    setReportData(map, reports)
  }, [map, styleVersion, reports])

  // Frame both routes (their union) whenever a new result arrives.
  useEffect(() => {
    if (!map || !fitKey) return
    const coordinates = [...(baseline?.coordinates ?? []), ...(walklah?.coordinates ?? [])]
    if (coordinates.length < 2) return
    const bounds = coordinates.reduce(
      (b, c) => b.extend(c),
      new maplibregl.LngLatBounds(coordinates[0], coordinates[0]),
    )
    map.fitBounds(bounds, { padding: cameraPadding(), maxZoom: 18, duration: 900 })
    // Only refit when the key changes, not on every geometry identity change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, fitKey])

  useEffect(() => {
    if (!map || !flyTarget) return
    map.flyTo({
      center: [flyTarget.longitude, flyTarget.latitude],
      zoom: Math.max(map.getZoom(), 17.5),
      padding: cameraPadding(),
      duration: 900,
    })
  }, [map, flyTarget])

  useEffect(() => {
    if (!map) return
    map.getCanvas().style.cursor = placing ? 'crosshair' : ''
  }, [map, placing])

  // Draft pin for a new report: draggable so the spot can be fine-tuned.
  useEffect(() => {
    if (!map || !draft) return
    const el = document.createElement('div')
    el.className = 'draft-pin'
    el.setAttribute('aria-label', 'New report location')
    const marker = new maplibregl.Marker({ element: el, anchor: 'bottom', draggable: true })
      .setLngLat([draft.longitude, draft.latitude])
      .addTo(map)
    marker.on('dragend', () => {
      const { lat, lng } = marker.getLngLat()
      live.current.onPlace({ latitude: lat, longitude: lng })
    })
    return () => {
      marker.remove()
    }
  }, [map, draft])

  // Label pills next to active obstacles so the reason for a detour reads at a glance.
  useEffect(() => {
    if (!map) return
    const pills = reports
      .filter((r) => STATUS_META[r.status]?.blocksRoutes)
      .map((r) => {
        const el = document.createElement('div')
        el.className = 'obstacle-pill'
        el.textContent = `${categoryLabel(r.category)} · ${STATUS_META[r.status].label}`
        return new maplibregl.Marker({ element: el, anchor: 'left', offset: [16, 0] })
          .setLngLat([r.longitude, r.latitude])
          .addTo(map)
      })
    return () => pills.forEach((m) => m.remove())
  }, [map, reports])

  // Destination markers (HTML markers, so they still render on the fallback style without fonts).
  useEffect(() => {
    if (!map) return
    const markers = destinations.map((d) => {
      const role = d.id === from ? 'origin' : d.id === to ? 'destination' : 'place'
      const el = document.createElement('div')
      el.className = `place-marker place-marker--${role}`
      const dot = document.createElement('span')
      dot.className = 'place-marker__dot'
      const label = document.createElement('span')
      label.className = 'place-marker__label'
      label.textContent = d.name
      el.append(dot, label)
      return new maplibregl.Marker({ element: el, anchor: 'left', offset: [-9, 0] })
        .setLngLat([d.longitude, d.latitude])
        .addTo(map)
    })
    return () => markers.forEach((m) => m.remove())
  }, [map, destinations, from, to])

  const recenter = () => map?.flyTo({ center: MAP_CENTER, zoom: MAP_ZOOM })

  return (
    <div className="map-view">
      <div ref={containerRef} className="map-view__canvas" />
      <div className="map-fabs">
        <button type="button" className="map-fab" onClick={onOpenSurvey} aria-label="Map data (S · Survey)">
          <Icon name="layers" size={20} />
        </button>
        <button type="button" className="map-fab" onClick={recenter} aria-label="Recentre on Universiti Malaya">
          <Icon name="locate" size={20} />
        </button>
      </div>
      {placing && (
        <div className="map-hint" role="status">
          <Icon name="pin" size={16} /> Tap the map where the problem is — drag the pin to adjust
        </div>
      )}
      {baseMapFailed && (
        <div className="map-notice" role="status">
          <Icon name="info" size={16} /> Base map unavailable — routes and reports still shown
        </div>
      )}
      <MapLegend show={reports.length > 0 || Boolean(baseline)} />
    </div>
  )
}

function MapLegend({ show }: { show: boolean }) {
  if (!show) return null
  return (
    <div className="map-legend" aria-label="Map legend">
      <span>
        <i className="map-legend__line map-legend__line--usual" /> Usual path
      </span>
      <span>
        <i className="map-legend__line map-legend__line--walklah" /> WalkLah route
      </span>
      {(['pending', 'verified_active', 'verified_cleared'] as const).map((s) => (
        <span key={s}>
          <i className="map-legend__dot" style={{ background: STATUS_META[s].color }} /> {STATUS_META[s].label}
        </span>
      ))}
    </div>
  )
}

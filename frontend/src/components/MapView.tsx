import * as maplibregl from 'maplibre-gl'
import type { Map as MapLibreMap, PaddingOptions } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { categoryLabel } from '../config/categories'
import { MAP_CENTER, MAP_STYLE_URL, MAP_ZOOM, MAX_BOUNDS } from '../config/map'
import { STATUS_META } from '../config/status'
import { applyWalkLahPalette, FALLBACK_STYLE } from '../map/palette'
import { ensureReportLayers, REPORTS_LAYER, setReportData, startReportPulse } from '../map/reportLayers'
import { reportPopupContent } from '../map/reportPopup'
import {
  ensureOverlayLayers,
  SELECTED_SEGMENTS_LAYER,
  setPilotRing,
  setRouteDisplay,
  setScenarioLink,
  startRouteFlow,
  type RouteDisplay,
} from '../map/routeLayers'
import type { LatLon, Report } from '../types'
import { Icon } from './icons'

const STYLE_TIMEOUT_MS = 10_000

// MapLibre finds its worker relative to its own module URL, which breaks once Vite pre-bundles
// the library, so point it at the (self-contained) worker file explicitly.
maplibregl.setWorkerUrl(workerUrl)

export interface FlyTarget extends LatLon {
  key: number
}

export interface PinMarker extends LatLon {
  kind: 'start' | 'end' | 'place'
  label: string
}

interface Props {
  /** Space taken by UI over the map (sheet, panels), relative to the map's own box. */
  padding: () => PaddingOptions
  routes?: RouteDisplay | null
  /** Changes whenever the camera should frame the current routes. */
  fitKey?: string | null
  reports?: Report[]
  pins?: PinMarker[]
  pilot?: { anchor: LatLon; radiusM: number } | null
  /** When set, map taps call onPick instead of inspecting segments. */
  picking?: boolean
  onPick?: (point: LatLon) => void
  draft?: LatLon | null
  onDraftMove?: (point: LatLon) => void
  link?: { start: LatLon | null; end: LatLon | null } | null
  flyTarget?: FlyTarget | null
  onSegmentTap?: (segmentId: string) => void
  /** Extra overlay controls (rendered top-right under the built-in ones). */
  children?: ReactNode
}

export function MapView(props: Props) {
  const { padding, routes = null, fitKey = null, reports = [], pins = [], pilot = null, picking = false } = props
  const { draft = null, link = null, flyTarget = null, children } = props
  const containerRef = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<MapLibreMap | null>(null)
  // Bumped each time a style finishes loading, so overlay data is re-applied after a style swap.
  const [styleVersion, setStyleVersion] = useState(0)
  const [baseMapFailed, setBaseMapFailed] = useState(false)

  // Latest callbacks for map event handlers that are bound once.
  const live = useRef(props)
  useEffect(() => {
    live.current = props
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
      new maplibregl.AttributionControl({ compact: true, customAttribution: '© OpenStreetMap contributors' }),
      'bottom-left',
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
      // Start the compact attribution collapsed (its "i" button opens it) so it doesn't cover the map.
      container.querySelector('.maplibregl-ctrl-attrib')?.classList.remove('maplibregl-compact-show')
      if (import.meta.env.DEV) (window as unknown as { __walklahMap?: MapLibreMap }).__walklahMap = instance
      if (!usingFallback) {
        styleLoaded = true
        applyWalkLahPalette(instance)
      }
      window.clearTimeout(timer)
      ensureOverlayLayers(instance)
      ensureReportLayers(instance)
      // Overlays only need the style, not every base tile: on slow wifi 'load' can take a long
      // time, but routes, reports and markers should appear as soon as possible.
      setMap(instance)
      setStyleVersion((v) => v + 1)
    })
    // Only a failure before the style has loaded triggers the fallback; later tile errors are ignored.
    instance.on('error', switchToFallback)

    let popup: maplibregl.Popup | null = null
    instance.on('click', (event) => {
      const current = live.current
      if (current.picking) {
        current.onPick?.({ latitude: event.lngLat.lat, longitude: event.lngLat.lng })
        return
      }
      const box: [maplibregl.PointLike, maplibregl.PointLike] = [
        [event.point.x - 6, event.point.y - 6],
        [event.point.x + 6, event.point.y + 6],
      ]
      const reportHit = instance.getLayer(REPORTS_LAYER)
        ? instance.queryRenderedFeatures(box, { layers: [REPORTS_LAYER] })[0]
        : undefined
      const report = reportHit && (current.reports ?? []).find((r) => r.id === reportHit.properties?.id)
      if (report) {
        popup?.remove()
        popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '240px' })
          .setLngLat([report.longitude, report.latitude])
          .setDOMContent(reportPopupContent(report))
          .addTo(instance)
        return
      }
      const segmentHit = instance.getLayer(SELECTED_SEGMENTS_LAYER)
        ? instance.queryRenderedFeatures(box, { layers: [SELECTED_SEGMENTS_LAYER] })[0]
        : undefined
      if (segmentHit?.properties?.id) current.onSegmentTap?.(String(segmentHit.properties.id))
    })
    for (const layer of [REPORTS_LAYER, SELECTED_SEGMENTS_LAYER]) {
      instance.on('mouseenter', layer, () => {
        if (!live.current.picking) instance.getCanvas().style.cursor = 'pointer'
      })
      instance.on('mouseleave', layer, () => {
        if (!live.current.picking) instance.getCanvas().style.cursor = ''
      })
    }

    // Keep the canvas sized to its box (the phone frame resizes with the window).
    const observer = new ResizeObserver(() => instance.resize())
    observer.observe(container)

    const stopFlow = startRouteFlow(instance)
    const stopPulse = startReportPulse(instance)

    return () => {
      window.clearTimeout(timer)
      observer.disconnect()
      stopFlow()
      stopPulse()
      popup?.remove()
      instance.remove()
      setMap(null)
    }
  }, [])

  // Route lines come only from API geometry; nothing is drawn when a route is missing.
  useEffect(() => {
    if (!map) return
    ensureOverlayLayers(map)
    setRouteDisplay(map, routes)
  }, [map, styleVersion, routes])

  useEffect(() => {
    if (!map) return
    ensureReportLayers(map)
    setReportData(map, reports)
  }, [map, styleVersion, reports])

  useEffect(() => {
    if (!map) return
    setPilotRing(map, pilot?.anchor ?? null, pilot?.radiusM ?? 0)
  }, [map, styleVersion, pilot])

  useEffect(() => {
    if (!map) return
    setScenarioLink(map, link?.start ?? null, link?.end ?? null)
  }, [map, styleVersion, link])

  // Frame all route options whenever a new result arrives.
  useEffect(() => {
    if (!map || !fitKey || !routes) return
    const coordinates = routes.routes.flatMap((r) => r.geometry.coordinates)
    if (coordinates.length < 2) return
    const bounds = coordinates.reduce(
      (b, c) => b.extend(c),
      new maplibregl.LngLatBounds(coordinates[0], coordinates[0]),
    )
    map.fitBounds(bounds, { padding: live.current.padding(), maxZoom: 17.5, duration: 900 })
    // Only refit when the key changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, fitKey])

  useEffect(() => {
    if (!map || !flyTarget) return
    map.flyTo({
      center: [flyTarget.longitude, flyTarget.latitude],
      zoom: Math.max(map.getZoom(), 17),
      padding: live.current.padding(),
      duration: 900,
    })
  }, [map, flyTarget])

  useEffect(() => {
    if (!map) return
    map.getCanvas().style.cursor = picking ? 'crosshair' : ''
  }, [map, picking])

  // Draft pin (report location / scenario point): draggable to fine-tune.
  useEffect(() => {
    if (!map || !draft) return
    const el = document.createElement('div')
    el.className = 'draft-pin'
    el.setAttribute('aria-label', 'Chosen location')
    const marker = new maplibregl.Marker({ element: el, anchor: 'bottom', draggable: Boolean(live.current.onDraftMove) })
      .setLngLat([draft.longitude, draft.latitude])
      .addTo(map)
    marker.on('dragend', () => {
      const { lat, lng } = marker.getLngLat()
      live.current.onDraftMove?.({ latitude: lat, longitude: lng })
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
        return new maplibregl.Marker({ element: el, anchor: 'left', offset: [14, 0] })
          .setLngLat([r.longitude, r.latitude])
          .addTo(map)
      })
    return () => pills.forEach((m) => m.remove())
  }, [map, reports])

  // Start / destination / place markers (HTML, so they still render on the fallback style).
  useEffect(() => {
    if (!map) return
    const markers = pins.map((p) => {
      const el = document.createElement('div')
      el.className = `place-marker place-marker--${p.kind}`
      const dot = document.createElement('span')
      dot.className = 'place-marker__dot'
      const label = document.createElement('span')
      label.className = 'place-marker__label'
      label.textContent = p.label
      el.append(dot, label)
      return new maplibregl.Marker({ element: el, anchor: 'left', offset: [-9, 0] })
        .setLngLat([p.longitude, p.latitude])
        .addTo(map)
    })
    return () => markers.forEach((m) => m.remove())
  }, [map, pins])

  const recenter = () => map?.flyTo({ center: MAP_CENTER, zoom: MAP_ZOOM, padding: padding() })

  return (
    <div className="map-view">
      <div ref={containerRef} className="map-view__canvas" />
      <div className="map-fabs">
        <button type="button" className="map-fab" onClick={recenter} aria-label="Recentre the map">
          <Icon name="locate" size={20} />
        </button>
        {children}
      </div>
      {baseMapFailed && (
        <div className="map-notice" role="status">
          <Icon name="info" size={16} /> Base map unavailable — routes and reports still shown
        </div>
      )}
    </div>
  )
}

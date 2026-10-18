import * as maplibregl from 'maplibre-gl'
import type { Map as MapLibreMap, PaddingOptions } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef, useState } from 'react'
import { MAP_CENTER, MAP_STYLE_URL, MAP_ZOOM, MAX_BOUNDS } from '../config/map'
import { applyWalkLahPalette, FALLBACK_STYLE } from '../map/palette'
import {
  BASELINE_SOURCE,
  ensureRouteLayers,
  setRouteData,
  setRouteFocus,
  startRouteFlow,
  WALKLAH_SOURCE,
} from '../map/routeLayers'
import type { Destination, LineStringGeometry } from '../types'
import { Icon } from './icons'

const STYLE_TIMEOUT_MS = 10_000

// MapLibre finds its worker relative to its own module URL, which breaks once Vite pre-bundles
// the library, so point it at the (self-contained) worker file explicitly.
maplibregl.setWorkerUrl(workerUrl)

interface Props {
  destinations: Destination[]
  from: string | null
  to: string | null
  baseline: LineStringGeometry | null
  walklah: LineStringGeometry | null
  focus: 'baseline' | 'walklah'
  /** Changes whenever the camera should frame the current routes. */
  fitKey: string | null
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

export function MapView({ destinations, from, to, baseline, walklah, focus, fitKey, onOpenSurvey }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<MapLibreMap | null>(null)
  // Bumped each time a style finishes loading, so overlay data is re-applied after a style swap.
  const [styleVersion, setStyleVersion] = useState(0)
  const [baseMapFailed, setBaseMapFailed] = useState(false)

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
      setStyleVersion((v) => v + 1)
    })
    // Only a failure before the style has loaded triggers the fallback; later tile errors are ignored.
    instance.on('error', switchToFallback)
    instance.once('load', () => setMap(instance))
    const stopFlow = startRouteFlow(instance)

    return () => {
      window.clearTimeout(timer)
      stopFlow()
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
      {baseMapFailed && (
        <div className="map-notice" role="status">
          <Icon name="info" size={16} /> Base map unavailable — routes and reports still shown
        </div>
      )}
    </div>
  )
}

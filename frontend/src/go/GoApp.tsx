import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import * as api from '../api/walklahApi'
import { BackendStatus, type BackendState } from '../components/BackendStatus'
import { MapView, type FlyTarget, type MapViewInfo, type PinMarker, type UserLocation } from '../components/MapView'
import { isInsideDataBounds, MAP_CENTER } from '../config/map'
import type { RouteDisplay } from '../map/routeLayers'
import type { LatLon, Pilot, PlannedRoute, Report, RouteMode, RoutesResponse } from '../types'
import { AboutSheet } from './AboutSheet'
import { DeviceFrame } from './DeviceFrame'
import { FeedbackSheet } from './FeedbackSheet'
import { GoNav } from './GoNav'
import { setLanguage, t } from './i18n'
import './i18n.ms'
import { atFor, loadPrefs, savePrefs, type GoPrefs, type TimeChoice } from './lib'
import { LocationPicker } from './LocationPicker'
import { CommunityScreen } from './screens/CommunityScreen'
import { ExploreScreen } from './screens/ExploreScreen'
import { HomeScreen } from './screens/HomeScreen'
import { ReportScreen } from './screens/ReportScreen'
import { WalkScreen } from './screens/WalkScreen'
import { SegmentSheet } from './SegmentSheet'
import type { Endpoint, GoTab, PickTarget } from './types'
import { readGoUrl, writeGoUrl } from './url'
import { useWeather } from './useWeather'
import './go.css'

export type RoutesState =
  | { status: 'idle' }
  | { status: 'loading'; key: string }
  | { status: 'ready'; key: string; data: RoutesResponse }
  | { status: 'error'; key: string; message: string }

/** Names a dropped pin after the nearest place or street ("Near ZUS Coffee", "Jalan Puteri 1/2"). */
async function nameForPin(point: LatLon): Promise<Pick<Endpoint, 'label' | 'area'>> {
  try {
    const found = await api.reverseLookup(point.latitude, point.longitude)
    if (found.name) return { label: found.label, area: found.area }
    return { label: t('Dropped pin'), area: found.area }
  } catch {
    return { label: t('Dropped pin'), area: null }
  }
}

export default function GoApp() {
  const initial = useRef(readGoUrl()).current
  const [tab, setTab] = useState<GoTab>(initial.tab)
  const [from, setFrom] = useState<Endpoint | null>(initial.from)
  const [to, setTo] = useState<Endpoint | null>(initial.to)
  const [timeChoice, setTimeChoice] = useState<TimeChoice>(initial.time)
  const [prefs, setPrefsState] = useState<GoPrefs>(loadPrefs)
  const [modeChoice, setModeChoice] = useState<RouteMode | null>(initial.mode)

  setLanguage(prefs.lang)

  const [backend, setBackend] = useState<BackendState>('checking')
  const [backendMessage, setBackendMessage] = useState<string | null>(null)
  const [pilot, setPilot] = useState<Pilot | null>(null)
  const [reports, setReports] = useState<Report[]>([])
  const [dataVersion, setDataVersion] = useState(0)

  const [pickerFor, setPickerFor] = useState<'from' | 'to' | null>(null)
  const [picking, setPicking] = useState<PickTarget | null>(null)
  const [reportPoint, setReportPoint] = useState<LatLon | null>(null)
  const [segmentId, setSegmentId] = useState<string | null>(null)
  const [aboutOpen, setAboutOpen] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [flyTarget, setFlyTarget] = useState<FlyTarget | null>(null)
  const [routesState, setRoutesState] = useState<RoutesState>({ status: 'idle' })
  const [view, setView] = useState<MapViewInfo | null>(null)

  // Walk mode: following the selected route with GPS (or a preview playback).
  const [walking, setWalking] = useState<{ preview: boolean } | null>(null)
  const [walkRoute, setWalkRoute] = useState<PlannedRoute | null>(null)
  const [userLocation, setUserLocation] = useState<UserLocation | null>(null)

  const sheetRef = useRef<HTMLDivElement>(null)
  const goRef = useRef<HTMLDivElement>(null)

  const setPrefs = useCallback((next: GoPrefs) => {
    setPrefsState(next)
    savePrefs(next)
  }, [])

  useEffect(() => {
    writeGoUrl({ tab, from, to, time: timeChoice, mode: modeChoice })
  }, [tab, from, to, timeChoice, modeChoice])

  // Start where the walker is, if they have already allowed location access (no prompt on load).
  useEffect(() => {
    if (initial.from || initial.to || !('geolocation' in navigator) || !navigator.permissions) return
    navigator.permissions.query({ name: 'geolocation' as PermissionName }).then(
      (status) => {
        if (status.state !== 'granted') return
        navigator.geolocation.getCurrentPosition((pos) => {
          const { latitude, longitude } = pos.coords
          if (isInsideDataBounds(latitude, longitude)) setFlyTarget({ latitude, longitude, key: Date.now() })
        })
      },
      () => undefined,
    )
  }, [initial])

  // ---- shared data ------------------------------------------------------

  const connect = useCallback(() => {
    return Promise.all([api.getHealth(), api.getPilot(), api.getReports()]).then(
      ([, nextPilot, nextReports]) => {
        setPilot(nextPilot)
        setReports(nextReports)
        setBackend('online')
        setBackendMessage(null)
      },
      (error: unknown) => {
        setBackend('offline')
        setBackendMessage(api.errorMessage(error))
      },
    )
  }, [])

  useEffect(() => {
    void connect()
  }, [connect])

  const refreshReports = useCallback(async () => {
    try {
      setReports(await api.getReports())
    } catch (error) {
      if (error instanceof api.ApiError && error.kind === 'network') {
        setBackend('offline')
        setBackendMessage(error.message)
      }
    }
    setDataVersion((v) => v + 1)
  }, [])

  // Another phone (or the operator) may have changed reports: refresh when the app is shown again.
  useEffect(() => {
    const onFocus = () => (backend === 'online' ? void refreshReports() : backend === 'offline' && void connect())
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [backend, refreshReports, connect])

  // ---- routes -----------------------------------------------------------

  const routeKey =
    from && to && backend === 'online'
      ? [from.latitude, from.longitude, to.latitude, to.longitude, timeChoice, prefs.stepFree, prefs.rain, dataVersion].join('|')
      : null

  useEffect(() => {
    if (!routeKey || !from || !to) return
    let cancelled = false
    api
      .getRoutes({
        start: from,
        end: to,
        at: atFor(timeChoice),
        stepFree: prefs.stepFree,
        shareStats: prefs.shareStats,
        rain: prefs.rain,
      })
      .then(
        (data) => !cancelled && setRoutesState({ status: 'ready', key: routeKey, data }),
        (error: unknown) => !cancelled && setRoutesState({ status: 'error', key: routeKey, message: api.errorMessage(error) }),
      )
    return () => {
      cancelled = true
    }
    // routeKey captures every input; prefs.shareStats only affects logging.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeKey])

  const routes: RoutesState = !routeKey
    ? { status: 'idle' }
    : routesState.status !== 'idle' && routesState.key === routeKey
      ? routesState
      : { status: 'loading', key: routeKey }

  const data = routes.status === 'ready' ? routes.data : null
  const planned = useMemo(
    () => (data?.routes.filter((r): r is PlannedRoute => r.available) ?? []),
    [data],
  )
  const defaultMode: RouteMode = prefs.walker === 'leisure' ? 'enjoyable' : 'practical'
  const selectedMode: RouteMode =
    modeChoice && planned.some((r) => r.mode === modeChoice)
      ? modeChoice
      : planned.some((r) => r.mode === defaultMode)
        ? defaultMode
        : 'shortest'
  const selectedRoute = planned.find((r) => r.mode === selectedMode) ?? null

  // While walking, keep showing the last route until a reroute arrives.
  useEffect(() => {
    if (walking && selectedRoute) setWalkRoute(selectedRoute)
  }, [walking, selectedRoute])

  const routeDisplay: RouteDisplay | null = useMemo(() => {
    if (walking && walkRoute) return { routes: [walkRoute], selected: walkRoute.mode, night: data ? !data.sun.daylight : false }
    return data && tab === 'explore' ? { routes: planned, selected: selectedMode, night: !data.sun.daylight } : null
  }, [data, planned, selectedMode, tab, walking, walkRoute])

  // ---- map ----------------------------------------------------------------

  const padding = useCallback(() => {
    const root = goRef.current?.getBoundingClientRect()
    const sheet = sheetRef.current?.getBoundingClientRect()
    const bottom = root && sheet ? Math.max(80, root.bottom - sheet.top + 16) : 320
    return { top: 70, right: 56, bottom, left: 30 }
  }, [])

  const pins = useMemo<PinMarker[]>(() => {
    const out: PinMarker[] = []
    if (tab !== 'home' && tab !== 'report') {
      if (from && !walking) out.push({ kind: 'start', label: from.label, latitude: from.latitude, longitude: from.longitude })
      if (to) out.push({ kind: 'end', label: to.label, latitude: to.latitude, longitude: to.longitude })
    }
    return out
  }, [from, to, tab, walking])

  const auditedRing = useMemo(
    () => (pilot ? { anchor: pilot.audited_area.anchor, radiusM: pilot.audited_area.radius_m } : null),
    [pilot],
  )

  const onPick = useCallback(
    (point: LatLon) => {
      if (picking === 'report') {
        setReportPoint(point)
        return
      }
      const target = picking
      const endpoint: Endpoint = { ...point, label: t('Dropped pin'), source: 'pin' }
      if (target === 'from') setFrom(endpoint)
      if (target === 'to') setTo(endpoint)
      setPicking(null)
      setModeChoice(null)
      void nameForPin(point).then((named) => {
        const update = (current: Endpoint | null) =>
          current && current.source === 'pin' && current.latitude === point.latitude && current.longitude === point.longitude
            ? { ...current, ...named }
            : current
        if (target === 'from') setFrom(update)
        if (target === 'to') setTo(update)
      })
    },
    [picking],
  )

  const chooseEndpoint = (which: 'from' | 'to', endpoint: Endpoint) => {
    if (which === 'from') setFrom(endpoint)
    else setTo(endpoint)
    setPickerFor(null)
    setModeChoice(null)
    setFlyTarget({ latitude: endpoint.latitude, longitude: endpoint.longitude, key: Date.now() })
  }

  const swap = () => {
    setFrom(to)
    setTo(from)
  }

  const changeTab = (next: GoTab) => {
    setTab(next)
    setPicking(next === 'report' ? 'report' : null)
    setSegmentId(null)
    if (backend === 'online') void refreshReports()
  }

  const startWalk = (preview: boolean) => {
    if (!selectedRoute) return
    setWalkRoute(selectedRoute)
    setWalking({ preview })
    setSegmentId(null)
  }

  const endWalk = () => {
    setWalking(null)
    setWalkRoute(null)
    setUserLocation(null)
  }

  // Off the route: plan again from where the walker is now.
  const reroute = useCallback((here: LatLon) => {
    setFrom({ ...here, label: t('Your location'), source: 'gps' })
  }, [])

  const fitKey = routes.status === 'ready' && tab === 'explore' && !walking ? `${routes.key}|${tab}` : null
  // Search suggestions are ranked around the walker if known, otherwise the map centre
  // (rounded to ~100 m so small pans don't refetch).
  const nearSource = userLocation ?? view?.center ?? { latitude: MAP_CENTER[1], longitude: MAP_CENTER[0] }
  const nearLat = Math.round(nearSource.latitude * 1000) / 1000
  const nearLon = Math.round(nearSource.longitude * 1000) / 1000
  const near = useMemo<LatLon>(() => ({ latitude: nearLat, longitude: nearLon }), [nearLat, nearLon])
  const weather = useWeather(near)

  return (
    <DeviceFrame>
      <div ref={goRef} className={`go go--${walking ? 'walk' : tab}${picking ? ' is-picking' : ''}`}>
        <MapView
          padding={padding}
          routes={routeDisplay}
          fitKey={fitKey}
          reports={reports}
          pins={pins}
          pilot={walking ? null : auditedRing}
          picking={picking !== null}
          onPick={onPick}
          draft={tab === 'report' && !walking ? reportPoint : null}
          onDraftMove={setReportPoint}
          flyTarget={flyTarget}
          onSegmentTap={tab === 'explore' && !walking ? setSegmentId : undefined}
          onViewChange={setView}
          userLocation={userLocation}
          follow={Boolean(walking)}
        >
          {!walking && (
            <button type="button" className="map-fab" onClick={() => setAboutOpen(true)} aria-label={t('About WalkLah and settings')}>
              <span className="map-fab__text">i</span>
            </button>
          )}
        </MapView>

        <BackendStatus state={backend} message={backendMessage} onRetry={() => { setBackend('checking'); void connect() }} />

        {picking && picking !== 'report' && (
          <div className="pick-banner" role="status">
            <span>{picking === 'from' ? t('Tap the map to set your start') : t('Tap the map to set your destination')}</span>
            <button type="button" className="btn btn--small btn--light" onClick={() => setPicking(null)}>
              {t('Cancel')}
            </button>
          </div>
        )}

        {walking && walkRoute ? (
          <WalkScreen
            route={walkRoute}
            destination={to?.label ?? t('Destination')}
            preview={walking.preview}
            onPreviewChange={(preview) => setWalking({ preview })}
            onPosition={setUserLocation}
            onReroute={reroute}
            onExit={endWalk}
            onReported={() => void refreshReports()}
          />
        ) : (
          <>
            {tab === 'home' && (
              <HomeScreen
                from={from}
                to={to}
                prefs={prefs}
                onPrefs={setPrefs}
                onOpenPicker={setPickerFor}
                onSwap={swap}
                onFindRoutes={() => changeTab('explore')}
                onAbout={() => setAboutOpen(true)}
              />
            )}

            {tab !== 'home' && (
              <section ref={sheetRef} className={`go-sheet go-sheet--${tab}`} aria-label="WalkLah">
                <div className="go-sheet__handle" aria-hidden="true" />
                {tab === 'explore' && (
                  <ExploreScreen
                    from={from}
                    to={to}
                    onOpenPicker={setPickerFor}
                    onSwap={swap}
                    timeChoice={timeChoice}
                    onTime={setTimeChoice}
                    prefs={prefs}
                    onPrefs={setPrefs}
                    routes={routes}
                    selected={selectedMode}
                    recommended={defaultMode}
                    onSelect={setModeChoice}
                    weather={weather.byHour}
                    onFeedback={() => setFeedbackOpen(true)}
                    onStartWalk={startWalk}
                  />
                )}
                {tab === 'report' && (
                  <ReportScreen
                    point={reportPoint}
                    onPoint={(p) => {
                      setReportPoint(p)
                      if (p) setFlyTarget({ ...p, key: Date.now() })
                    }}
                    onSubmitted={async () => {
                      setReportPoint(null)
                      await refreshReports()
                    }}
                    onCommunity={() => changeTab('community')}
                  />
                )}
                {tab === 'community' && (
                  <CommunityScreen
                    reports={reports}
                    near={near}
                    onChanged={refreshReports}
                    onShowOnMap={(r) => setFlyTarget({ latitude: r.latitude, longitude: r.longitude, key: Date.now() })}
                    onReport={() => changeTab('report')}
                  />
                )}
              </section>
            )}

            <GoNav active={tab} onChange={changeTab} />
          </>
        )}

        {pickerFor && (
          <LocationPicker
            which={pickerFor}
            near={near}
            featured={pilot?.featured ?? []}
            onChoose={(endpoint) => chooseEndpoint(pickerFor, endpoint)}
            onPickOnMap={() => {
              setPicking(pickerFor)
              setPickerFor(null)
              if (tab === 'home') setTab('explore')
            }}
            onClose={() => setPickerFor(null)}
          />
        )}
        {segmentId && (
          <SegmentSheet segmentId={segmentId} at={atFor(timeChoice)} onClose={() => setSegmentId(null)} />
        )}
        {aboutOpen && <AboutSheet pilot={pilot} prefs={prefs} onPrefs={setPrefs} onClose={() => setAboutOpen(false)} />}
        {feedbackOpen && <FeedbackSheet mode={selectedMode} onClose={() => setFeedbackOpen(false)} />}
      </div>
    </DeviceFrame>
  )
}

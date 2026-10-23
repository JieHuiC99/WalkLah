import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import * as api from '../../api/walklahApi'
import { Icon, type IconName } from '../../components/icons'
import type { UserLocation } from '../../components/MapView'
import { isInsideDataBounds } from '../../config/map'
import type { LatLon, PlannedRoute, Report, RouteAlert, RouteStep } from '../../types'
import { preparePhoto } from '../../utils/photo'
import { language, t } from '../i18n'
import { deviceId, distanceLabel } from '../lib'
import { alertText, stepText } from '../describe'
import { pointAt, project, routeLine } from '../walk'

const OFF_ROUTE_M = 35
const OFF_ROUTE_S = 10
const ARRIVE_M = 15
const ALERT_AHEAD_M = 120
const PREVIEW_SPEED_MPS = 9 // ~7x walking pace, so a preview takes a minute or two
const TICK_MS = 250

const STEP_ICONS: Record<string, IconName> = {
  left: 'turnLeft',
  right: 'turnRight',
  'sharp left': 'turnLeft',
  'sharp right': 'turnRight',
  'slight left': 'slightLeft',
  'slight right': 'slightRight',
}

const ALERT_ICONS: Record<RouteAlert['type'], IconName> = {
  sun: 'sun',
  unlit: 'moon',
  light_unknown: 'bulb',
  uncovered: 'umbrella',
  steps: 'stairs',
  crossing: 'crossing',
  hazard: 'alert',
}

const QUICK_REPORTS: { category: string; label: string; icon: IconName }[] = [
  { category: 'blocked_walkway', label: 'Blocked', icon: 'barrier' },
  { category: 'flooding', label: 'Flooded', icon: 'flood' },
  { category: 'lighting_out', label: 'Dark here', icon: 'moon' },
]

function stepIcon(step: RouteStep): IconName {
  if (step.type === 'arrive') return 'flagEnd'
  if (step.type === 'steps') return 'stairs'
  if (step.type === 'depart') return 'navigation'
  return (step.modifier && STEP_ICONS[step.modifier]) || 'straight'
}

function speak(text: string) {
  if (!('speechSynthesis' in window)) return
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = language() === 'ms' ? 'ms-MY' : 'en-MY'
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(utterance)
}

interface Props {
  route: PlannedRoute
  destination: string
  /** Play the walk along the route instead of following GPS (laptop, rehearsal). */
  preview: boolean
  onPreviewChange: (preview: boolean) => void
  onPosition: (location: UserLocation | null) => void
  onReroute: (from: LatLon) => void
  onExit: () => void
  onReported: () => void
}

export function WalkScreen({ route, destination, preview, onPreviewChange, onPosition, onReroute, onExit, onReported }: Props) {
  const line = useMemo(() => routeLine(route.geometry.coordinates), [route])
  const [along, setAlong] = useState(0)
  const [offset, setOffset] = useState(0)
  const [position, setPosition] = useState<LatLon | null>(null)
  const [paused, setPaused] = useState(false)
  const [watchError, setGpsError] = useState<string | null>(null)
  const gpsError = 'geolocation' in navigator ? watchError : t('This browser has no location access.')
  const [voice, setVoice] = useState(false)
  const [showSteps, setShowSteps] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  // The report just sent from walk mode, so a photo can be added to it with one more tap.
  const [lastReport, setLastReport] = useState<Report | null>(null)
  const toastTimer = useRef<number | null>(null)
  const photoInput = useRef<HTMLInputElement>(null)
  const [feedback, setFeedback] = useState<'idle' | 'sent'>('idle')
  const offSince = useRef<number | null>(null)
  const alongRef = useRef(0)
  const announced = useRef<Set<string>>(new Set())
  const live = useRef({ onPosition, onReroute })
  useEffect(() => {
    live.current = { onPosition, onReroute }
  })

  // A new route (after a reroute) starts from the walker's projected position.
  useEffect(() => {
    announced.current = new Set()
    offSince.current = null
  }, [route])

  // ---- position source: GPS ------------------------------------------------
  useEffect(() => {
    if (preview || !('geolocation' in navigator)) return
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const here = { latitude: pos.coords.latitude, longitude: pos.coords.longitude }
        if (!isInsideDataBounds(here.latitude, here.longitude)) {
          setGpsError(t("You're outside Malaysia. Use Preview to play the walk instead."))
          return
        }
        setGpsError(null)
        const progress = project(line, here, alongRef.current)
        alongRef.current = Math.max(alongRef.current - 20, progress.along)
        setAlong(alongRef.current)
        setOffset(progress.offset)
        setPosition(here)
        live.current.onPosition({ ...here, accuracy: pos.coords.accuracy, heading: pos.coords.heading })
        // Off the route for a while (and not just GPS noise): plan again from here.
        if (progress.offset > Math.max(OFF_ROUTE_M, pos.coords.accuracy)) {
          offSince.current ??= Date.now()
          if (Date.now() - offSince.current > OFF_ROUTE_S * 1000) {
            offSince.current = null
            live.current.onReroute(here)
          }
        } else {
          offSince.current = null
        }
      },
      (error) =>
        setGpsError(
          error.code === error.PERMISSION_DENIED
            ? t('Location permission was denied. Use Preview to play the walk instead.')
            : t("Couldn't get your location yet…"),
        ),
      { enableHighAccuracy: true, maximumAge: 2_000, timeout: 20_000 },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [preview, line])

  // ---- position source: preview playback ----------------------------------
  useEffect(() => {
    if (!preview) return
    const timer = window.setInterval(() => {
      if (paused) return
      const next = Math.min(line.total, alongRef.current + (PREVIEW_SPEED_MPS * TICK_MS) / 1000)
      alongRef.current = next
      const { point, heading } = pointAt(line, next)
      setAlong(next)
      setOffset(0)
      setPosition(point)
      live.current.onPosition({ ...point, heading })
    }, TICK_MS)
    return () => window.clearInterval(timer)
  }, [preview, paused, line])

  useEffect(() => () => live.current.onPosition(null), [])

  // ---- derived state -------------------------------------------------------
  const arrived = along >= line.total - ARRIVE_M && position !== null
  const steps = route.steps
  const nextIndex = steps.findIndex((s) => s.type !== 'depart' && s.at_m > along + 3)
  const next = along < 10 ? steps[0] : steps[nextIndex >= 0 ? nextIndex : steps.length - 1]
  const toNext = next ? Math.max(0, next.at_m - along) : 0
  const remaining = Math.max(0, route.distance_m - along)
  const pace = route.distance_m / Math.max(route.estimated_minutes * 60, 1)
  const minutesLeft = remaining / pace / 60
  const upcoming = route.alerts.filter((a) => a.at_m >= along - 5 && a.at_m - along <= ALERT_AHEAD_M)

  // Announce each alert and turn once (screen readers via aria-live; voice when switched on).
  const [announcement, setAnnouncement] = useState('')
  useEffect(() => {
    for (const alert of upcoming) {
      const key = `a:${alert.type}:${alert.at_m}`
      if (announced.current.has(key)) continue
      announced.current.add(key)
      const text = `${alertText(alert)}${alert.at_m - along > 15 ? ` — ${t('in {d}', { d: distanceLabel(alert.at_m - along) })}` : ''}`
      setAnnouncement(text)
      if (voice) speak(text)
    }
    if (next && next.type !== 'depart' && toNext < 40) {
      const key = `s:${next.at_m}`
      if (!announced.current.has(key)) {
        announced.current.add(key)
        setAnnouncement(stepText(next))
        if (voice) speak(stepText(next))
      }
    }
  }, [upcoming, next, toNext, along, voice])

  const quickReport = async (category: string) => {
    if (!position) return setToast(t('Waiting for your location…'))
    try {
      const report = await api.createReport({
        category,
        description: null,
        latitude: position.latitude,
        longitude: position.longitude,
        device: deviceId(),
      })
      setToast(report.merged ? t('Added your confirmation to an existing report. Thanks!') : t('Reported here. Thanks!'))
      setLastReport(report.has_photo ? null : report)
      onReported()
    } catch (error) {
      setToast(api.errorMessage(error))
      setLastReport(null)
    }
    hideToastLater(12_000)
  }

  const hideToastLater = (ms: number) => {
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => {
      setToast(null)
      setLastReport(null)
    }, ms)
  }

  const addPhoto = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !lastReport) return
    try {
      setToast(t('Sending photo…'))
      await api.addReportPhoto(lastReport.id, await preparePhoto(file), deviceId())
      setToast(t('Photo added. Thanks!'))
      setLastReport(null)
      onReported()
    } catch (error) {
      setToast(error instanceof Error ? error.message : t("That photo couldn't be read. Try JPEG or PNG."))
    }
    hideToastLater(4000)
  }

  const sendFeedback = async (passable: 'yes' | 'partly' | 'no') => {
    try {
      await api.sendFeedback(route.mode, passable, null, deviceId(), position)
    } finally {
      setFeedback('sent')
    }
  }

  if (arrived) {
    return (
      <section className="walk walk--arrived" aria-label={t('Arrived')}>
        <div className="walk-arrive">
          <span className="walk-arrive__icon">
            <Icon name="flagEnd" size={26} />
          </span>
          <h2>{t('You have arrived')}</h2>
          <p>{destination}</p>
          {feedback === 'sent' ? (
            <p className="walk-arrive__thanks">
              <Icon name="check" size={18} /> {t('Thanks — this helps check the routes against reality.')}
            </p>
          ) : (
            <>
              <p className="muted">{t('Was the route passable all the way?')}</p>
              <div className="segmented segmented--three">
                {(['yes', 'partly', 'no'] as const).map((v) => (
                  <button key={v} type="button" onClick={() => void sendFeedback(v)}>
                    {t({ yes: 'Yes', partly: 'Partly', no: 'No' }[v])}
                  </button>
                ))}
              </div>
            </>
          )}
          <button type="button" className="btn btn--primary btn--block" onClick={onExit}>
            {t('Done')}
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="walk" aria-label={t('Walking')}>
      <div className="walk-instruction" aria-live="off">
        {next && (
          <>
            <span className="walk-instruction__icon">
              <Icon name={stepIcon(next)} size={34} />
            </span>
            <div className="walk-instruction__text">
              {next.type !== 'depart' && <span className="walk-instruction__dist">{distanceLabel(toNext)}</span>}
              <strong>{stepText(next)}</strong>
            </div>
          </>
        )}
      </div>
      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>

      {upcoming.length > 0 && (
        <ul className="walk-alerts">
          {upcoming.slice(0, 2).map((a) => (
            <li key={`${a.type}-${a.at_m}`} className={`walk-alert walk-alert--${a.type}`}>
              <Icon name={ALERT_ICONS[a.type]} size={16} />
              <span>{alertText(a)}</span>
              <small>{a.at_m - along > 10 ? distanceLabel(a.at_m - along) : t('now')}</small>
            </li>
          ))}
        </ul>
      )}

      <div className="walk-panel">
        {gpsError && !preview && (
          <p className="inline-error walk-panel__error">
            {gpsError}{' '}
            <button type="button" className="link-btn" onClick={() => onPreviewChange(true)}>
              {t('Preview')}
            </button>
          </p>
        )}
        {!preview && offset > OFF_ROUTE_M && <p className="walk-panel__off">{t('Off the route — finding a new one if you keep going…')}</p>}
        <div className="walk-panel__summary">
          <div>
            <strong>{Math.max(1, Math.round(minutesLeft))} min</strong>
            <span>
              {distanceLabel(remaining)} · {destination}
            </span>
          </div>
          {preview && (
            <button type="button" className="icon-btn icon-btn--soft" onClick={() => setPaused(!paused)} aria-label={paused ? t('Play') : t('Pause')}>
              <Icon name={paused ? 'play' : 'pause'} size={18} />
            </button>
          )}
          <button
            type="button"
            className={`icon-btn icon-btn--soft${voice ? ' is-on' : ''}`}
            onClick={() => setVoice(!voice)}
            aria-pressed={voice}
            aria-label={t('Voice alerts')}
            title={t('Voice alerts')}
          >
            <Icon name="message" size={18} />
          </button>
          <button type="button" className="btn btn--small walk-panel__end" onClick={onExit}>
            {t('End')}
          </button>
        </div>

        <div className="walk-quick" role="group" aria-label={t('Report at your position')}>
          {QUICK_REPORTS.map((q) => (
            <button key={q.category} type="button" className="walk-quick__btn" onClick={() => void quickReport(q.category)}>
              <Icon name={q.icon} size={16} /> {t(q.label)}
            </button>
          ))}
        </div>
        {toast && (
          <p className="walk-toast" role="status">
            {toast}
            {lastReport && (
              <button type="button" className="link-btn walk-toast__photo" onClick={() => photoInput.current?.click()}>
                <Icon name="camera" size={14} /> {t('Add photo')}
              </button>
            )}
          </p>
        )}
        <input ref={photoInput} type="file" accept="image/*" capture="environment" hidden onChange={(e) => void addPhoto(e)} />

        <button type="button" className="walk-steps-toggle" onClick={() => setShowSteps(!showSteps)} aria-expanded={showSteps}>
          {showSteps ? t('Hide steps') : t('All steps ({n})', { n: steps.length })}
        </button>
        {showSteps && (
          <ol className="walk-steps">
            {steps.map((s, i) => (
              <li key={i} className={s === next ? 'is-current' : s.at_m < along ? 'is-done' : ''}>
                <Icon name={stepIcon(s)} size={16} />
                <span>{stepText(s)}</span>
                {s.distance_m > 0 && <small>{distanceLabel(s.distance_m)}</small>}
              </li>
            ))}
          </ol>
        )}
        {preview && <p className="fine-print center">{t('Preview: playing the walk along the route.')}</p>}
      </div>
    </section>
  )
}

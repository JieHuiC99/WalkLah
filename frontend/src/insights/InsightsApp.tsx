import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import * as api from '../api/walklahApi'
import type { StepStage } from '../app/navigation'
import { Icon } from '../components/icons'
import { MapView, type FlyTarget } from '../components/MapView'
import { StepRail } from '../components/StepRail'
import type { LatLon, Overview, Pilot, Report } from '../types'
import { ExploreStage } from './stages/ExploreStage'
import { PrioritiseStage } from './stages/PrioritiseStage'
import { SurveyStage } from './stages/SurveyStage'
import { TrackStage } from './stages/TrackStage'
import './insights.css'

const KEY_STORAGE = 'walklah.operatorKey'

// Insights is open by default. A deployment can require an operator key (WALKLAH_OPERATOR_KEY on
// the server); only then does the app ask for it, and keeps it for this browser session.
function readKey(): string {
  try {
    return window.sessionStorage.getItem(KEY_STORAGE) ?? ''
  } catch {
    return ''
  }
}

function forgetKey(): void {
  try {
    window.sessionStorage.removeItem(KEY_STORAGE)
  } catch {
    // ignore
  }
}

function readStage(): StepStage {
  const s = new URLSearchParams(window.location.search).get('stage')
  return s === 'S' || s === 'T' || s === 'E' || s === 'P' ? s : 'T'
}

/** Map interaction requested by a stage: placing a closure, or the two ends of a hypothetical link. */
export type MapPick = { purpose: 'closure' } | { purpose: 'link-start' } | { purpose: 'link-end' }

export interface StageProps {
  operatorKey: string
  overview: Overview | null
  reports: Report[]
  refresh: () => Promise<void>
  flyTo: (point: LatLon) => void
  startPick: (pick: MapPick | null) => void
  pick: MapPick | null
  picked: { closure: LatLon | null; linkStart: LatLon | null; linkEnd: LatLon | null }
  clearPicked: () => void
}

export default function InsightsApp() {
  const [key, setKey] = useState<string>(readKey)
  const [needKey, setNeedKey] = useState(false)
  const [stage, setStage] = useState<StepStage>(readStage)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [reports, setReports] = useState<Report[]>([])
  const [pilot, setPilot] = useState<Pilot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [flyTarget, setFlyTarget] = useState<FlyTarget | null>(null)
  const [pick, setPick] = useState<MapPick | null>(null)
  const [picked, setPicked] = useState<StageProps['picked']>({ closure: null, linkStart: null, linkEnd: null })

  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    p.set('app', 'insights')
    p.set('stage', stage)
    window.history.replaceState(null, '', `${window.location.pathname}?${p}`)
  }, [stage])

  const refresh = useCallback(async () => {
    try {
      const [o, r] = await Promise.all([api.getOverview(key), api.getReports()])
      setOverview(o)
      setReports(r)
      setError(null)
    } catch (e) {
      if (e instanceof api.ApiError && e.status === 401) {
        forgetKey()
        setNeedKey(true)
      }
      setError(api.errorMessage(e))
    }
  }, [key])

  useEffect(() => {
    let cancelled = false
    Promise.all([api.getOverview(key), api.getReports(), api.getPilot()]).then(
      ([o, r, p]) => {
        if (cancelled) return
        setOverview(o)
        setReports(r)
        setPilot(p)
      },
      (e: unknown) => {
        if (cancelled) return
        if (e instanceof api.ApiError && e.status === 401) setNeedKey(true)
        else setError(api.errorMessage(e))
      },
    )
    return () => {
      cancelled = true
    }
  }, [key])

  const onPick = useCallback(
    (point: LatLon) => {
      if (!pick) return
      setPicked((prev) =>
        pick.purpose === 'closure'
          ? { ...prev, closure: point }
          : pick.purpose === 'link-start'
            ? { ...prev, linkStart: point }
            : { ...prev, linkEnd: point },
      )
      setPick(pick.purpose === 'link-start' ? { purpose: 'link-end' } : null)
    },
    [pick],
  )

  const pilotRing = useMemo(() => (pilot ? { anchor: pilot.anchor, radiusM: pilot.radius_m } : null), [pilot])
  const link = useMemo(
    () => (stage === 'P' && (picked.linkStart || picked.linkEnd) ? { start: picked.linkStart, end: picked.linkEnd } : null),
    [stage, picked.linkStart, picked.linkEnd],
  )
  const draft = stage === 'T' ? picked.closure : stage === 'P' ? (picked.linkEnd ?? picked.linkStart) : null
  const padding = useCallback(() => ({ top: 60, right: 60, bottom: 60, left: 60 }), [])

  if (needKey) {
    return (
      <KeyGate
        onKey={(k) => {
          setKey(k)
          setNeedKey(false)
          setError(null)
        }}
      />
    )
  }

  const stageProps: StageProps = {
    operatorKey: key,
    overview,
    reports,
    refresh,
    flyTo: (point) => setFlyTarget({ ...point, key: Date.now() }),
    startPick: setPick,
    pick,
    picked,
    clearPicked: () => setPicked({ closure: null, linkStart: null, linkEnd: null }),
  }

  return (
    <div className="insights">
      <header className="insights__header">
        <div className="insights__brand">
          <span className="brand-tile">
            <Icon name="chart" size={20} />
          </span>
          <span>
            <strong>
              Walk<em>Lah</em> Insights
            </strong>
            <small>Township operator view{pilot?.coverage_area === 'malaysia' ? ' · Malaysia' : ''}</small>
          </span>
        </div>
        <div className="insights__rail">
          <StepRail current={stage} tone="dark" onSelect={setStage} />
        </div>
        <div className="insights__links">
          <a href="./" className="btn btn--small btn--light">
            <Icon name="walk" size={16} /> WalkLah Go
          </a>
          {key && (
            <button
              type="button"
              className="btn btn--small btn--ghost insights__signout"
              onClick={() => {
                forgetKey()
                setKey('')
                setNeedKey(true)
              }}
            >
              <Icon name="lock" size={16} /> Sign out
            </button>
          )}
        </div>
      </header>
      {error && (
        <p className="insights__error" role="alert">
          {error}
        </p>
      )}
      <main className="insights__main">
        <section className="insights__panel" aria-label="Stage">
          {stage === 'S' && <SurveyStage {...stageProps} />}
          {stage === 'T' && <TrackStage {...stageProps} />}
          {stage === 'E' && <ExploreStage {...stageProps} />}
          {stage === 'P' && <PrioritiseStage {...stageProps} />}
        </section>
        <section className="insights__map" aria-label="Map">
          <MapView
            padding={padding}
            reports={reports}
            pilot={pilotRing}
            picking={pick !== null}
            onPick={onPick}
            draft={draft}
            link={link}
            flyTarget={flyTarget}
          />
          {pick && (
            <div className="pick-banner insights__pick" role="status">
              <span>
                {pick.purpose === 'closure'
                  ? 'Click the map where the closure is'
                  : pick.purpose === 'link-start'
                    ? 'Click where the new walkway starts'
                    : 'Click where the new walkway ends'}
              </span>
              <button type="button" className="btn btn--small btn--light" onClick={() => setPick(null)}>
                Cancel
              </button>
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

function KeyGate({ onKey }: { onKey: (key: string) => void }) {
  const [value, setValue] = useState('')
  const [checking, setChecking] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setChecking(true)
    setMessage(null)
    try {
      await api.getOverview(value.trim())
      try {
        window.sessionStorage.setItem(KEY_STORAGE, value.trim())
      } catch {
        // key just won't survive a reload
      }
      onKey(value.trim())
    } catch (e) {
      setMessage(e instanceof api.ApiError && e.status === 401 ? 'That operator key is not right.' : api.errorMessage(e))
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="key-gate">
      <form className="key-gate__card" onSubmit={submit}>
        <span className="brand-tile">
          <Icon name="lock" size={20} />
        </span>
        <h1>WalkLah Insights</h1>
        <p>This WalkLah server is set up for named operators only. Enter the operator key from your administrator.</p>
        <label className="go-field">
          <span className="go-label">Operator key</span>
          <input
            className="text-input"
            type="password"
            value={value}
            autoComplete="current-password"
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        {message && <p className="inline-error">{message}</p>}
        <button type="submit" className="btn btn--primary btn--block" disabled={!value.trim() || checking}>
          {checking ? 'Checking…' : 'Open Insights'}
        </button>
        <a href="./" className="key-gate__back">
          ← Back to WalkLah Go
        </a>
      </form>
    </div>
  )
}

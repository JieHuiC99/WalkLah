import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import * as api from '../api/walklahApi'
import type { StepStage } from '../app/navigation'
import { Icon } from '../components/icons'
import { MapView, type FlyTarget, type HeatPoint, type MapViewInfo } from '../components/MapView'
import { StepRail } from '../components/StepRail'
import type { LatLon, Overview, Pilot, Report, ScenarioResult, Trends } from '../types'
import { PrintReport } from './PrintReport'
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
  /** Reports inside the selected area. */
  reports: Report[]
  /** "west,south,east,north" of the selected area, or null for all of Malaysia. */
  bbox: string | null
  trends: Trends | null
  refresh: () => Promise<void>
  flyTo: (point: LatLon) => void
  startPick: (pick: MapPick | null) => void
  pick: MapPick | null
  picked: { closure: LatLon | null; linkStart: LatLon | null; linkEnd: LatLon | null }
  clearPicked: () => void
  onScenario: (result: ScenarioResult | null) => void
}

type HeatKind = 'off' | 'reports' | 'trips'

function inBox(bbox: string | null, p: LatLon): boolean {
  if (!bbox) return true
  const [w, s, e, n] = bbox.split(',').map(Number)
  return p.latitude >= s && p.latitude <= n && p.longitude >= w && p.longitude <= e
}

export default function InsightsApp() {
  const [key, setKey] = useState<string>(readKey)
  const [needKey, setNeedKey] = useState(false)
  const [stage, setStage] = useState<StepStage>(readStage)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [allReports, setReports] = useState<Report[]>([])
  const [trends, setTrends] = useState<Trends | null>(null)
  const [pilot, setPilot] = useState<Pilot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [flyTarget, setFlyTarget] = useState<FlyTarget | null>(null)
  const [pick, setPick] = useState<MapPick | null>(null)
  const [picked, setPicked] = useState<StageProps['picked']>({ closure: null, linkStart: null, linkEnd: null })
  const [view, setView] = useState<MapViewInfo | null>(null)
  const [areaMode, setAreaMode] = useState<'view' | 'all'>('view')
  const [heatKind, setHeatKind] = useState<HeatKind>('off')
  const [heat, setHeat] = useState<HeatPoint[] | null>(null)
  const [scenario, setScenario] = useState<ScenarioResult | null>(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    p.set('app', 'insights')
    p.set('stage', stage)
    window.history.replaceState(null, '', `${window.location.pathname}?${p}`)
  }, [stage])

  // The selected area follows the map (rounded so tiny pans don't refetch).
  const bbox =
    areaMode === 'view' && view ? view.bounds.map((v) => v.toFixed(3)).join(',') : null

  const fail = useCallback((e: unknown) => {
    if (e instanceof api.ApiError && e.status === 401) {
      forgetKey()
      setNeedKey(true)
    } else {
      setError(api.errorMessage(e))
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [o, r, tr] = await Promise.all([api.getOverview(key, bbox), api.getReports(), api.getTrends(key, bbox)])
      setOverview(o)
      setReports(r)
      setTrends(tr)
      setError(null)
    } catch (e) {
      fail(e)
    }
  }, [key, bbox, fail])

  useEffect(() => {
    let cancelled = false
    Promise.all([api.getOverview(key, bbox), api.getReports(), api.getTrends(key, bbox)]).then(
      ([o, r, tr]) => {
        if (cancelled) return
        setOverview(o)
        setReports(r)
        setTrends(tr)
        setError(null)
      },
      (e: unknown) => !cancelled && fail(e),
    )
    return () => {
      cancelled = true
    }
  }, [key, bbox, fail])

  useEffect(() => {
    let cancelled = false
    api.getPilot().then(
      (p) => !cancelled && setPilot(p),
      () => undefined,
    )
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (heatKind === 'off') return
    let cancelled = false
    api.getHeat(key, bbox, heatKind).then(
      (h) => !cancelled && setHeat(h.points),
      (e: unknown) => !cancelled && fail(e),
    )
    return () => {
      cancelled = true
    }
  }, [key, bbox, heatKind, allReports, fail])

  const reports = useMemo(() => allReports.filter((r) => inBox(bbox, r)), [allReports, bbox])

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

  const auditedRing = useMemo(
    () => (pilot ? { anchor: pilot.audited_area.anchor, radiusM: pilot.audited_area.radius_m } : null),
    [pilot],
  )
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
    bbox,
    trends,
    refresh,
    flyTo: (point) => setFlyTarget({ ...point, key: Date.now() }),
    startPick: setPick,
    pick,
    picked,
    clearPicked: () => setPicked({ closure: null, linkStart: null, linkEnd: null }),
    onScenario: setScenario,
  }

  const exportCsv = async () => {
    setExporting(true)
    try {
      await api.downloadReportsCsv(key, bbox)
    } catch (e) {
      fail(e)
    } finally {
      setExporting(false)
    }
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
              Walk<em>Lah</em>
            </strong>
            <small>Township operator view{pilot?.coverage_area === 'malaysia' ? ' · Malaysia' : ''}</small>
          </span>
        </div>
        <div className="insights__rail">
          <StepRail current={stage} tone="dark" onSelect={setStage} />
        </div>
        <div className="insights__links">
          <button type="button" className="btn btn--small btn--light" onClick={() => void exportCsv()} disabled={exporting}>
            <Icon name="download" size={16} /> {exporting ? 'Exporting…' : 'Export CSV'}
          </button>
          <button type="button" className="btn btn--small btn--light" onClick={() => window.print()}>
            <Icon name="book" size={16} /> Print report
          </button>
          <a href="./" className="btn btn--small btn--light">
            <Icon name="walk" size={16} /> Walker view
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
          <div className="area-bar">
            <div className="segmented segmented--two" role="radiogroup" aria-label="Area">
              <button
                type="button"
                role="radio"
                aria-checked={areaMode === 'view'}
                className={areaMode === 'view' ? 'is-active' : ''}
                onClick={() => setAreaMode('view')}
              >
                This map area
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={areaMode === 'all'}
                className={areaMode === 'all' ? 'is-active' : ''}
                onClick={() => setAreaMode('all')}
              >
                All of Malaysia
              </button>
            </div>
            <p className="muted small">
              {areaMode === 'view'
                ? 'Numbers below cover what the map shows. Pan or zoom to your township.'
                : 'Numbers below cover every report and opted-in trip.'}
            </p>
          </div>
          {stage === 'S' && <SurveyStage {...stageProps} />}
          {stage === 'T' && <TrackStage {...stageProps} />}
          {stage === 'E' && <ExploreStage {...stageProps} />}
          {stage === 'P' && <PrioritiseStage {...stageProps} />}
        </section>
        <section className="insights__map" aria-label="Map">
          <MapView
            padding={padding}
            reports={allReports}
            pilot={auditedRing}
            picking={pick !== null}
            onPick={onPick}
            draft={draft}
            link={link}
            flyTarget={flyTarget}
            onViewChange={setView}
            heat={heatKind === 'off' ? null : heat}
          />
          <div className="heat-toggle segmented" role="radiogroup" aria-label="Heatmap">
            {(['off', 'reports', 'trips'] as HeatKind[]).map((k) => (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={heatKind === k}
                className={heatKind === k ? 'is-active' : ''}
                onClick={() => setHeatKind(k)}
              >
                {{ off: 'No heatmap', reports: 'Reports', trips: 'Trips hit' }[k]}
              </button>
            ))}
          </div>
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
      <PrintReport overview={overview} trends={trends} scenario={scenario} bbox={bbox} />
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
        <h1>WalkLah</h1>
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
          ← Back to the walker view
        </a>
      </form>
    </div>
  )
}

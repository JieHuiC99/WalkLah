import { useCallback, useEffect, useState } from 'react'
import * as api from './api/walklahApi'
import { readUrlState, writeUrlState, type StepStage, type Tab } from './app/navigation'
import { BackendStatus, type BackendState } from './components/BackendStatus'
import { BottomNav } from './components/BottomNav'
import { MapView, type FlyTarget, type LatLon } from './components/MapView'
import { SurveySheet } from './components/SurveySheet'
import { DEMO_OBSTACLE } from './config/demo'
import { useRoutes } from './hooks/useRoutes'
import { CommunityPage } from './pages/CommunityPage'
import { DashboardPage } from './pages/DashboardPage'
import { HomePage } from './pages/HomePage'
import { NavigatePage } from './pages/NavigatePage'
import { ReportPage } from './pages/ReportPage'
import type { Destination, InsightsSummary, Report } from './types'

const STAGE_TAB: Record<Exclude<StepStage, 'S'>, Tab> = { T: 'report', E: 'explore', P: 'operator' }

async function loadShared() {
  await api.getHealth()
  const [destinations, reports, summary] = await Promise.all([api.getDestinations(), api.getReports(), api.getSummary()])
  return { destinations, reports, summary }
}

export default function App() {
  const [tab, setTab] = useState<Tab>(() => readUrlState().tab)
  const [from, setFrom] = useState<string | null>(() => readUrlState().from)
  const [to, setTo] = useState<string | null>(() => readUrlState().to)
  const [surveyOpen, setSurveyOpen] = useState(false)
  const [draft, setDraft] = useState<LatLon | null>(null)
  const [flyTarget, setFlyTarget] = useState<FlyTarget | null>(null)

  const [backend, setBackend] = useState<BackendState>('checking')
  const [backendMessage, setBackendMessage] = useState<string | null>(null)
  const [destinations, setDestinations] = useState<Destination[]>([])
  const [reports, setReports] = useState<Report[]>([])
  const [summary, setSummary] = useState<InsightsSummary | null>(null)
  // Bumped after every mutation so routes and other derived views refetch.
  const [dataVersion, setDataVersion] = useState(0)

  useEffect(() => {
    writeUrlState({ tab, from, to })
  }, [tab, from, to])

  // Loads everything the screens share; state is only set once the network answers.
  const connect = useCallback(() => {
    return loadShared().then(
      (shared) => {
        setDestinations(shared.destinations)
        setReports(shared.reports)
        setSummary(shared.summary)
        setBackend('online')
        setBackendMessage(null)
        setDataVersion((v) => v + 1)
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

  const retry = useCallback(() => {
    setBackend('checking')
    void connect()
  }, [connect])

  /** Refetches reports + summary. Network failures switch the banner on. */
  const refreshAll = useCallback(async () => {
    try {
      const [nextReports, nextSummary] = await Promise.all([api.getReports(), api.getSummary()])
      setReports(nextReports)
      setSummary(nextSummary)
    } catch (error) {
      if (error instanceof api.ApiError && error.kind === 'network') {
        setBackend('offline')
        setBackendMessage(error.message)
      }
    }
  }, [])

  /** Every mutation (report, verify, reset) ends here so all views and routes refresh. */
  const afterMutation = useCallback(async () => {
    await refreshAll()
    setDataVersion((v) => v + 1)
  }, [refreshAll])

  const goToStage = useCallback((stage: StepStage) => {
    if (stage === 'S') setSurveyOpen(true)
    else setTab(STAGE_TAB[stage])
  }, [])

  const swap = useCallback(() => {
    setFrom(to)
    setTo(from)
  }, [from, to])

  const flyTo = useCallback((point: LatLon) => {
    setFlyTarget({ latitude: point.latitude, longitude: point.longitude, key: Date.now() })
  }, [])

  const routes = useRoutes(from, to, dataVersion, backend === 'online')
  const [focus, setFocus] = useState<'baseline' | 'walklah'>('walklah')
  const routePair = routes.status === 'ready' ? routes.routes : null

  return (
    <div className={`shell shell--${tab}`}>
      <div className="map-area">
        <MapView
          destinations={destinations}
          from={from}
          to={to}
          baseline={routePair?.baseline?.geometry ?? null}
          walklah={routePair?.walklah?.geometry ?? null}
          focus={focus}
          fitKey={tab === 'explore' ? (routePair?.key ?? null) : null}
          reports={reports}
          placing={tab === 'report'}
          draft={tab === 'report' ? draft : null}
          onPlace={setDraft}
          flyTarget={flyTarget}
          onOpenSurvey={() => setSurveyOpen(true)}
        />
      </div>
      <BackendStatus state={backend} message={backendMessage} onRetry={retry} />

      <aside className="panel" aria-label="WalkLah">
        <div className="panel__body">
          {tab === 'home' && (
            <HomePage
              destinations={destinations}
              from={from}
              to={to}
              onFromChange={setFrom}
              onToChange={setTo}
              onSwap={swap}
              onFindRoute={() => setTab('explore')}
              onStage={goToStage}
            />
          )}
          {tab === 'explore' && (
            <NavigatePage
              destinations={destinations}
              from={from}
              to={to}
              onFromChange={setFrom}
              onToChange={setTo}
              onSwap={swap}
              routes={routes}
              focus={focus}
              onFocus={setFocus}
              reportCount={reports.length}
              onOpenCommunity={() => setTab('community')}
              onStage={goToStage}
            />
          )}
          {tab === 'report' && (
            <ReportPage
              draft={draft}
              onUseDemoSpot={() => {
                setDraft({ ...DEMO_OBSTACLE })
                flyTo(DEMO_OBSTACLE)
              }}
              onClearDraft={() => setDraft(null)}
              onSubmitted={async () => {
                setDraft(null)
                await afterMutation()
              }}
              onOpenCommunity={() => setTab('community')}
              onStage={goToStage}
            />
          )}
          {tab === 'community' && (
            <CommunityPage reports={reports} onShowOnMap={flyTo} onReport={() => setTab('report')} onStage={goToStage} />
          )}
          {tab === 'operator' && (
            <DashboardPage
              summary={summary}
              reports={reports}
              destinations={destinations}
              dataVersion={dataVersion}
              onChanged={afterMutation}
              onShowOnMap={(report) => {
                setTab('explore')
                flyTo(report)
              }}
              onStage={goToStage}
            />
          )}
        </div>
        <BottomNav active={tab} onChange={setTab} />
      </aside>

      <SurveySheet open={surveyOpen} destinations={destinations} onClose={() => setSurveyOpen(false)} />
    </div>
  )
}

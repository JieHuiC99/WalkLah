import { useCallback, useEffect, useState } from 'react'
import * as api from './api/walklahApi'
import { readUrlState, writeUrlState, type StepStage, type Tab } from './app/navigation'
import { BackendStatus, type BackendState } from './components/BackendStatus'
import { BottomNav } from './components/BottomNav'
import { MapView } from './components/MapView'
import { ScreenHeader } from './components/ScreenHeader'
import { SurveySheet } from './components/SurveySheet'
import { HomePage } from './pages/HomePage'
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

  const goToStage = useCallback((stage: StepStage) => {
    if (stage === 'S') setSurveyOpen(true)
    else setTab(STAGE_TAB[stage])
  }, [])

  const swap = useCallback(() => {
    setFrom(to)
    setTo(from)
  }, [from, to])

  return (
    <div className={`shell shell--${tab}`} data-version={dataVersion}>
      <div className="map-area">
        <MapView destinations={destinations} from={from} to={to} onOpenSurvey={() => setSurveyOpen(true)} />
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
          {tab === 'explore' && <ScreenHeader title="Route options" stage="E" onStage={goToStage} />}
          {tab === 'report' && <ScreenHeader title="Report an issue" stage="T" onStage={goToStage} />}
          {tab === 'community' && (
            <ScreenHeader title="Community updates" subtitle={`${reports.length} reports near Universiti Malaya`} stage="T" onStage={goToStage} />
          )}
          {tab === 'operator' && (
            <ScreenHeader
              title="Operator view"
              subtitle={summary ? `${summary.total_reports} reports · ${summary.active_obstacles} active obstacles` : undefined}
              stage="P"
              tone="dark"
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

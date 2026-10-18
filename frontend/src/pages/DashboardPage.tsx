import { useState } from 'react'
import * as api from '../api/walklahApi'
import type { StepStage } from '../app/navigation'
import { CategoryIcon } from '../components/CategoryIcon'
import { Icon } from '../components/icons'
import { ScreenHeader } from '../components/ScreenHeader'
import { StatusBadge } from '../components/StatusBadge'
import { categoryLabel } from '../config/categories'
import { statusMeta } from '../config/status'
import { useConnectionCheck } from '../hooks/useConnectionCheck'
import type { Destination, InsightsSummary, Report, ReportStatus, VerifyStatus } from '../types'
import { formatMetres, formatRelative, formatSigned } from '../utils/format'
import { newestFirst } from '../utils/reports'

const ACTIONS: Record<ReportStatus, { label: string; status: VerifyStatus; primary?: boolean }[]> = {
  pending: [
    { label: 'Verify as active obstacle', status: 'verified_active', primary: true },
    { label: 'Dispute', status: 'disputed' },
  ],
  verified_active: [
    { label: 'Mark cleared', status: 'verified_cleared', primary: true },
    { label: 'Mark stale', status: 'stale' },
  ],
  verified_cleared: [{ label: 'Reactivate', status: 'verified_active' }],
  disputed: [{ label: 'Reactivate', status: 'verified_active' }],
  stale: [{ label: 'Reactivate', status: 'verified_active' }],
}

interface Props {
  summary: InsightsSummary | null
  reports: Report[]
  destinations: Destination[]
  dataVersion: number
  onChanged: () => Promise<void>
  onShowOnMap: (report: Report) => void
  onStage: (stage: StepStage) => void
}

export function DashboardPage({ summary, reports, destinations, dataVersion, onChanged, onShowOnMap, onStage }: Props) {
  const [busy, setBusy] = useState<string | null>(null)
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)
  const { check, run } = useConnectionCheck()

  const verify = async (report: Report, status: VerifyStatus) => {
    setBusy(report.id)
    setRowError(null)
    try {
      await api.verifyReport(report.id, status)
      await onChanged()
    } catch (error) {
      setRowError({ id: report.id, message: api.errorMessage(error) })
    } finally {
      setBusy(null)
    }
  }

  const reset = async () => {
    setBusy('reset')
    setResetError(null)
    try {
      await api.resetDemo()
      await onChanged()
      setConfirmReset(false)
    } catch (error) {
      setResetError(api.errorMessage(error))
    } finally {
      setBusy(null)
    }
  }

  const placeName = (id: string) => destinations.find((d) => d.id === id)?.name ?? id
  const cards: { label: string; value: number | undefined; tone?: 'alert' }[] = [
    { label: 'Total reports', value: summary?.total_reports },
    { label: 'Pending', value: summary?.pending_reports },
    { label: 'Active obstacles', value: summary?.active_obstacles, tone: 'alert' },
    { label: 'Cleared', value: summary?.cleared_reports },
    { label: 'Affected path segments', value: summary?.affected_segments },
  ]
  const checkStale = check.state === 'done' && check.version !== dataVersion

  return (
    <div className="dashboard">
      <ScreenHeader
        title="Operator view"
        subtitle="WalkLah Insights · Universiti Malaya pilot"
        stage="P"
        tone="dark"
        onStage={onStage}
      />

      <p className="demo-label">
        <Icon name="info" size={16} /> Demo data — reports are simulated; verification is a demo operator action, not a
        physical inspection.
      </p>

      <div className="stat-cards">
        {cards.map((card) => (
          <div key={card.label} className={`stat-card${card.tone === 'alert' && (card.value ?? 0) > 0 ? ' stat-card--alert' : ''}`}>
            <span className="stat-card__value">{card.value ?? '—'}</span>
            <span className="stat-card__label">{card.label}</span>
          </div>
        ))}
      </div>

      <section className="panel-card" aria-labelledby="connections-heading">
        <div className="section-head">
          <h2 id="connections-heading">Affected connections</h2>
          <button
            type="button"
            className="btn btn--small btn--dark"
            disabled={check.state === 'running' || destinations.length < 2}
            onClick={() => void run(destinations, dataVersion)}
          >
            {check.state === 'running' ? (
              <>
                <span className="spinner" aria-hidden="true" /> {check.done}/{check.total}
              </>
            ) : (
              <>
                <Icon name="route" size={16} /> Check {(destinations.length * (destinations.length - 1)) / 2} pairs
              </>
            )}
          </button>
        </div>
        <ConnectionResults check={check} stale={checkStale} placeName={placeName} />
      </section>

      <section aria-labelledby="reports-heading">
        <div className="section-head">
          <h2 id="reports-heading">Reports</h2>
          <span className="muted small">Newest first</span>
        </div>
        {reports.length === 0 ? (
          <p className="empty-note">No reports yet. Reports submitted from the Report tab appear here.</p>
        ) : (
          <ul className="ops-list">
            {newestFirst(reports).map((report) => (
              <li key={report.id} className="ops-row" style={{ borderLeftColor: statusMeta(report.status).color }}>
                <div className="ops-row__head">
                  <StatusBadge status={report.status} />
                  <span className="muted small">{formatRelative(report.created_at)}</span>
                </div>
                <div className="ops-row__body">
                  <CategoryIcon category={report.category} size={20} />
                  <div className="ops-row__text">
                    <strong>{categoryLabel(report.category)}</strong>
                    {report.description && <p>{report.description}</p>}
                    <span className="ops-row__meta">
                      {report.latitude.toFixed(5)}, {report.longitude.toFixed(5)} ·{' '}
                      <code title="Footpath segment the server linked this report to">seg {report.segment_id}</code>
                    </span>
                  </div>
                </div>
                <div className="ops-row__actions">
                  {ACTIONS[report.status].map((action) => (
                    <button
                      key={action.status}
                      type="button"
                      className={`btn btn--small${action.primary ? ' btn--dark' : ''}`}
                      disabled={busy !== null}
                      onClick={() => void verify(report, action.status)}
                    >
                      {busy === report.id ? <span className="spinner" aria-hidden="true" /> : null}
                      {action.label}
                    </button>
                  ))}
                  <button type="button" className="link-button" onClick={() => onShowOnMap(report)}>
                    <Icon name="pin" size={14} /> Show on map
                  </button>
                </div>
                {rowError?.id === report.id && (
                  <p className="inline-error" role="alert">
                    {rowError.message}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="reset-zone">
        {confirmReset ? (
          <div className="reset-confirm" role="group" aria-label="Confirm reset">
            <span>Remove all reports from the demo server?</span>
            <div className="button-row">
              <button type="button" className="btn btn--small" onClick={() => setConfirmReset(false)} disabled={busy === 'reset'}>
                Cancel
              </button>
              <button type="button" className="btn btn--small btn--danger" onClick={() => void reset()} disabled={busy === 'reset'}>
                {busy === 'reset' && <span className="spinner" aria-hidden="true" />} Yes, reset
              </button>
            </div>
          </div>
        ) : (
          <button type="button" className="btn btn--small" onClick={() => setConfirmReset(true)} disabled={busy !== null}>
            <Icon name="refresh" size={16} /> Reset demo data
          </button>
        )}
        {resetError && (
          <p className="inline-error" role="alert">
            {resetError}
          </p>
        )}
      </section>
    </div>
  )
}

function ConnectionResults({
  check,
  stale,
  placeName,
}: {
  check: ReturnType<typeof useConnectionCheck>['check']
  stale: boolean
  placeName: (id: string) => string
}) {
  if (check.state === 'idle') {
    return <p className="muted small">Checks every pair of demo places for detours caused by verified obstacles.</p>
  }
  if (check.state === 'running') {
    return (
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={check.total} aria-valuenow={check.done}>
        <span style={{ width: `${(check.done / Math.max(1, check.total)) * 100}%` }} />
      </div>
    )
  }
  if (check.state === 'error') {
    return (
      <p className="inline-error" role="alert">
        {check.error}
      </p>
    )
  }
  return (
    <div className="connections">
      {stale && <p className="stale-note">Reports changed since this check — run it again for current numbers.</p>}
      <p className="muted small">
        {check.results.length === 0
          ? `No verified obstacles affect the ${check.total} demo connections.`
          : `${check.results.length} of ${check.total} place pairs are affected by verified obstacles.`}
        {check.failures > 0 ? ` ${check.failures} pair(s) could not be checked.` : ''}
      </p>
      {check.results.length > 0 && (
        <ul className="connection-list">
          {check.results.map((r) => (
            <li key={`${r.fromId}-${r.toId}`}>
              <span className="connection-list__pair">
                {placeName(r.fromId)} <Icon name="arrowRight" size={14} /> {placeName(r.toId)}
              </span>
              {r.noAlternative ? (
                <span className="status-badge status-badge--red status-badge--small">No walkable route</span>
              ) : (
                <span className="connection-list__delta">
                  {formatSigned(r.extraMetres ?? 0, 'm')} · {formatSigned(r.extraMinutes ?? 0, 'min', 1)}
                  <span className="muted"> ({formatMetres(r.baselineMetres)} → {formatMetres(r.walklahMetres ?? 0)})</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

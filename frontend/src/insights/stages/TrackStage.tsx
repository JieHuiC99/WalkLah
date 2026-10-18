import { useState, type FormEvent } from 'react'
import * as api from '../../api/walklahApi'
import { CategoryIcon } from '../../components/CategoryIcon'
import { Icon } from '../../components/icons'
import { StatusBadge } from '../../components/StatusBadge'
import { CATEGORIES, categoryLabel } from '../../config/categories'
import { statusMeta } from '../../config/status'
import type { Report, ReportEvent, ReportStatus, VerifyStatus } from '../../types'
import { formatRelative } from '../../utils/format'
import type { StageProps } from '../InsightsApp'
import { StageHeader } from './StageHeader'

const ACTIONS: Record<ReportStatus, { label: string; status: VerifyStatus; primary?: boolean }[]> = {
  pending: [
    { label: 'Verify as active', status: 'verified_active', primary: true },
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

const EVENT_LABELS: Record<string, string> = {
  reported: 'Reported by a walker',
  operator_closure: 'Entered by the operator',
  confirmed_still_there: 'A walker said it is still there',
  confirmed_cleared: 'A walker said it is cleared',
  verified_active: 'Verified as active',
  verified_cleared: 'Marked cleared',
  disputed: 'Disputed',
  stale: 'Marked stale',
}

/** Open work first: pending with most 'still there' votes, then active, then the rest by date. */
function queueOrder(a: Report, b: Report): number {
  const rank = (r: Report) => ({ pending: 0, verified_active: 1, disputed: 2, stale: 3, verified_cleared: 4 })[r.status]
  return rank(a) - rank(b) || b.confirmations.still_there - a.confirmations.still_there || b.created_at.localeCompare(a.created_at)
}

export function TrackStage({ operatorKey, overview, reports, refresh, flyTo, startPick, pick, picked, clearPicked }: StageProps) {
  const [busy, setBusy] = useState<string | null>(null)
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null)
  const [evidence, setEvidence] = useState<Record<string, string>>({})
  const [history, setHistory] = useState<Record<string, ReportEvent[] | 'loading'>>({})
  const [confirmReset, setConfirmReset] = useState(false)

  const act = async (report: Report, status: VerifyStatus) => {
    setBusy(report.id)
    setRowError(null)
    try {
      await api.verifyReport(operatorKey, report.id, status, evidence[report.id])
      setEvidence((e) => ({ ...e, [report.id]: '' }))
      setHistory((h) => {
        const next = { ...h }
        delete next[report.id]
        return next
      })
      await refresh()
    } catch (e) {
      setRowError({ id: report.id, message: api.errorMessage(e) })
    } finally {
      setBusy(null)
    }
  }

  const toggleHistory = async (report: Report) => {
    if (history[report.id]) {
      setHistory((h) => {
        const next = { ...h }
        delete next[report.id]
        return next
      })
      return
    }
    setHistory((h) => ({ ...h, [report.id]: 'loading' }))
    try {
      const events = await api.getReportHistory(report.id)
      setHistory((h) => ({ ...h, [report.id]: events }))
    } catch {
      setHistory((h) => ({ ...h, [report.id]: [] }))
    }
  }

  const counts = overview?.track.reports_by_status ?? {}
  return (
    <div className="stage">
      <StageHeader letter="T" title="Track" lead="Walker reports, community votes and official closures — verified by your team." />

      <div className="tile-grid tile-grid--five">
        {(
          [
            ['Pending', counts.pending ?? 0],
            ['Active', counts.verified_active ?? 0],
            ['Cleared', counts.verified_cleared ?? 0],
            ['Stale / disputed', (counts.stale ?? 0) + (counts.disputed ?? 0)],
            ['Votes', (overview?.track.still_there_votes ?? 0) + (overview?.track.cleared_votes ?? 0)],
          ] as [string, number][]
        ).map(([label, value]) => (
          <div key={label} className={`tile${label === 'Active' && value > 0 ? ' tile--alert' : ''}`}>
            <span className="tile__value">{value}</span>
            <span className="tile__label">{label}</span>
          </div>
        ))}
      </div>

      <p className="demo-label">
        <Icon name="info" size={16} /> Demo data — verification here stands in for a site check by township staff.
      </p>

      {reports.length === 0 ? (
        <p className="empty-note">No reports yet. Reports from WalkLah Go appear here.</p>
      ) : (
        <ul className="ops-list">
          {[...reports].sort(queueOrder).map((report) => {
            const events = history[report.id]
            return (
              <li key={report.id} className="ops-row" style={{ borderLeftColor: statusMeta(report.status).color }}>
                <div className="ops-row__head">
                  <StatusBadge status={report.status} />
                  <span className="muted small">
                    {report.source === 'operator' ? 'Operator · ' : ''}
                    {formatRelative(report.created_at)} · {report.temporary_or_permanent}
                  </span>
                </div>
                <div className="ops-row__body">
                  <CategoryIcon category={report.category} size={20} />
                  <div className="ops-row__text">
                    <strong>{categoryLabel(report.category)}</strong>
                    {report.description && <p>{report.description}</p>}
                    <span className="ops-row__meta">
                      {report.confirmations.still_there} still there · {report.confirmations.cleared} cleared ·{' '}
                      <code>seg {report.segment_id}</code>
                    </span>
                  </div>
                </div>
                <div className="ops-row__actions">
                  <input
                    className="text-input text-input--small"
                    placeholder="Evidence note (optional)"
                    value={evidence[report.id] ?? ''}
                    maxLength={280}
                    onChange={(e) => setEvidence((v) => ({ ...v, [report.id]: e.target.value }))}
                  />
                  {ACTIONS[report.status].map((action) => (
                    <button
                      key={action.status}
                      type="button"
                      className={`btn btn--small${action.primary ? ' btn--dark' : ''}`}
                      disabled={busy !== null}
                      onClick={() => void act(report, action.status)}
                    >
                      {busy === report.id && <span className="spinner" aria-hidden="true" />}
                      {action.label}
                    </button>
                  ))}
                  <button type="button" className="link-button" onClick={() => flyTo(report)}>
                    <Icon name="pin" size={14} /> Map
                  </button>
                  <button type="button" className="link-button" onClick={() => void toggleHistory(report)}>
                    <Icon name="clock" size={14} /> History
                  </button>
                </div>
                {rowError?.id === report.id && <p className="inline-error">{rowError.message}</p>}
                {events && (
                  <ol className="history">
                    {events === 'loading' ? (
                      <li>Loading…</li>
                    ) : (
                      events.map((e, i) => (
                        <li key={i}>
                          <span>{EVENT_LABELS[e.event_type] ?? e.event_type}</span>
                          <span className="muted small">
                            {e.verifier_role} · {formatRelative(e.time)}
                            {e.evidence_reference ? ` · “${e.evidence_reference}”` : ''}
                          </span>
                        </li>
                      ))
                    )}
                  </ol>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <ClosureForm
        operatorKey={operatorKey}
        point={picked.closure}
        picking={pick?.purpose === 'closure'}
        onPick={() => startPick({ purpose: 'closure' })}
        onDone={async () => {
          clearPicked()
          await refresh()
        }}
      />

      <section className="reset-zone">
        {confirmReset ? (
          <div className="reset-confirm" role="group" aria-label="Confirm reset">
            <span>Remove all reports, votes and history from the demo server?</span>
            <div className="button-row">
              <button type="button" className="btn btn--small" onClick={() => setConfirmReset(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn--small btn--danger"
                onClick={async () => {
                  await api.resetDemo(operatorKey)
                  setConfirmReset(false)
                  await refresh()
                }}
              >
                Yes, reset
              </button>
            </div>
          </div>
        ) : (
          <button type="button" className="btn btn--small" onClick={() => setConfirmReset(true)}>
            <Icon name="refresh" size={16} /> Reset demo data
          </button>
        )}
      </section>
    </div>
  )
}

function ClosureForm({
  operatorKey,
  point,
  picking,
  onPick,
  onDone,
}: {
  operatorKey: string
  point: { latitude: number; longitude: number } | null
  picking: boolean
  onPick: () => void
  onDone: () => Promise<void>
}) {
  const [category, setCategory] = useState('construction')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!point) return setError('Click the map to place the closure first.')
    setSaving(true)
    setError(null)
    try {
      await api.createClosure(operatorKey, { category, description: description.trim() || null, ...point })
      setDescription('')
      await onDone()
    } catch (e) {
      setError(api.errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Official closure or works</h2>
      <p className="muted small">Known works or closures from the township: active immediately, marked as an official update.</p>
      <div className="closure-row">
        <button type="button" className={`btn btn--small${picking ? ' btn--dark' : ''}`} onClick={onPick}>
          <Icon name="pin" size={16} /> {point ? 'Move on map' : 'Place on map'}
        </button>
        <select className="text-input text-input--small" value={category} onChange={(e) => setCategory(e.target.value)}>
          {CATEGORIES.filter((c) => c.value !== 'other').map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </div>
      <input
        className="text-input"
        placeholder="Description, e.g. drain works until Friday"
        value={description}
        maxLength={280}
        onChange={(e) => setDescription(e.target.value)}
      />
      {error && <p className="inline-error">{error}</p>}
      <button type="submit" className="btn btn--small btn--primary" disabled={saving}>
        {saving ? 'Saving…' : 'Add closure'}
      </button>
    </form>
  )
}

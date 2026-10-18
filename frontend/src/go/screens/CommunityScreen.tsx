import { useState } from 'react'
import * as api from '../../api/walklahApi'
import { CategoryIcon } from '../../components/CategoryIcon'
import { Icon } from '../../components/icons'
import { StatusBadge } from '../../components/StatusBadge'
import { categoryLabel } from '../../config/categories'
import { statusMeta } from '../../config/status'
import type { Report, ReportStatus } from '../../types'
import { formatRelative } from '../../utils/format'
import { newestFirst } from '../../utils/reports'
import { deviceId } from '../lib'

type Filter = 'open' | 'active' | 'pending' | 'closed'

const FILTERS: { id: Filter; label: string; statuses: ReportStatus[] }[] = [
  { id: 'open', label: 'Open', statuses: ['pending', 'verified_active'] },
  { id: 'active', label: 'Verified', statuses: ['verified_active'] },
  { id: 'pending', label: 'Pending', statuses: ['pending'] },
  { id: 'closed', label: 'Closed', statuses: ['verified_cleared', 'disputed', 'stale'] },
]

function expiresIn(report: Report): string | null {
  if (!report.expires_at || !['pending', 'verified_active'].includes(report.status)) return null
  const ms = Date.parse(report.expires_at.replace(/(\.\d{3})\d+/, '$1')) - Date.now()
  if (Number.isNaN(ms) || ms <= 0) return null
  const hours = Math.floor(ms / 3_600_000)
  return hours >= 1 ? `Expires in ${hours} h unless reconfirmed` : 'Expires within the hour unless reconfirmed'
}

interface Props {
  reports: Report[]
  onChanged: () => Promise<void>
  onShowOnMap: (report: Report) => void
  onReport: () => void
}

export function CommunityScreen({ reports, onChanged, onShowOnMap, onReport }: Props) {
  const [filter, setFilter] = useState<Filter>('open')
  const [busy, setBusy] = useState<string | null>(null)
  const [voted, setVoted] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<{ id: string; message: string } | null>(null)
  const active = FILTERS.find((f) => f.id === filter)!
  const visible = newestFirst(reports).filter((r) => active.statuses.includes(r.status))

  const vote = async (report: Report, stillThere: boolean) => {
    setBusy(report.id)
    setError(null)
    try {
      await api.confirmReport(report.id, stillThere, deviceId())
      setVoted((v) => ({ ...v, [report.id]: stillThere }))
      await onChanged()
    } catch (err) {
      setError({ id: report.id, message: api.errorMessage(err) })
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="go-screen">
      <h1 className="go-title">Community updates</h1>
      <p className="go-subtitle">Reports from walkers near Universiti Malaya</p>

      <div className="filter-pills" role="tablist" aria-label="Filter by status">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            role="tab"
            aria-selected={filter === f.id}
            className={filter === f.id ? 'is-active' : ''}
            onClick={() => setFilter(f.id)}
          >
            {f.label} <span className="filter-pills__count">{reports.filter((r) => f.statuses.includes(r.status)).length}</span>
          </button>
        ))}
      </div>

      {reports.length === 0 ? (
        <div className="empty-state">
          <Icon name="shoe" size={32} />
          <strong>No reports yet</strong>
          <p>Seen a blocked path, flooding or a broken light? Let the next walker know.</p>
          <button type="button" className="btn btn--primary" onClick={onReport}>
            Report an issue
          </button>
        </div>
      ) : visible.length === 0 ? (
        <p className="empty-note">Nothing here right now.</p>
      ) : (
        <ul className="report-list">
          {visible.map((report) => {
            const open = report.status === 'pending' || report.status === 'verified_active'
            const myVote = voted[report.id]
            const expiry = expiresIn(report)
            return (
              <li key={report.id} className="report-item" style={{ borderLeftColor: statusMeta(report.status).color }}>
                <CategoryIcon category={report.category} size={22} />
                <div className="report-item__body">
                  <div className="report-item__top">
                    <strong>{categoryLabel(report.category)}</strong>
                    <span className="muted small">{formatRelative(report.created_at)}</span>
                  </div>
                  {report.description && <p className="report-item__description">{report.description}</p>}
                  <div className="report-item__meta">
                    <StatusBadge status={report.status} size="small" />
                    {report.source === 'operator' && <span className="muted small">Official update</span>}
                    <button type="button" className="link-button" onClick={() => onShowOnMap(report)}>
                      <Icon name="pin" size={14} /> Map
                    </button>
                  </div>
                  {(report.confirmations.still_there > 0 || report.confirmations.cleared > 0) && (
                    <p className="muted small">
                      {report.confirmations.still_there} still there · {report.confirmations.cleared} say cleared
                    </p>
                  )}
                  {expiry && <p className="muted small">{expiry}</p>}
                  {open && (
                    <div className="vote-row">
                      <button
                        type="button"
                        className={`vote vote--still${myVote === true ? ' is-mine' : ''}`}
                        disabled={busy === report.id}
                        onClick={() => void vote(report, true)}
                      >
                        Still there
                      </button>
                      <button
                        type="button"
                        className={`vote vote--cleared${myVote === false ? ' is-mine' : ''}`}
                        disabled={busy === report.id}
                        onClick={() => void vote(report, false)}
                      >
                        Cleared
                      </button>
                    </div>
                  )}
                  {error?.id === report.id && <p className="inline-error">{error.message}</p>}
                </div>
              </li>
            )
          })}
        </ul>
      )}
      <p className="fine-print">
        Votes help operators decide what to check first. Only operator-verified obstacles change routes.
      </p>
    </div>
  )
}

import { useState } from 'react'
import type { StepStage } from '../app/navigation'
import { CategoryIcon } from '../components/CategoryIcon'
import { Icon } from '../components/icons'
import { ScreenHeader } from '../components/ScreenHeader'
import { StatusBadge } from '../components/StatusBadge'
import { categoryLabel, durationLabel } from '../config/categories'
import { statusMeta } from '../config/status'
import type { Report, ReportStatus } from '../types'
import { formatRelative } from '../utils/format'
import { newestFirst } from '../utils/reports'

type Filter = 'all' | 'active' | 'pending' | 'cleared' | 'closed'

const FILTERS: { id: Filter; label: string; statuses: ReportStatus[] | null }[] = [
  { id: 'all', label: 'All', statuses: null },
  { id: 'active', label: 'Active', statuses: ['verified_active'] },
  { id: 'pending', label: 'Pending', statuses: ['pending'] },
  { id: 'cleared', label: 'Cleared', statuses: ['verified_cleared'] },
  { id: 'closed', label: 'Disputed / stale', statuses: ['disputed', 'stale'] },
]

interface Props {
  reports: Report[]
  onShowOnMap: (report: Report) => void
  onReport: () => void
  onStage: (stage: StepStage) => void
}

export function CommunityPage({ reports, onShowOnMap, onReport, onStage }: Props) {
  const [filter, setFilter] = useState<Filter>('all')
  const active = FILTERS.find((f) => f.id === filter)!
  const visible = newestFirst(reports).filter((r) => !active.statuses || active.statuses.includes(r.status))

  return (
    <div className="community">
      <ScreenHeader title="Community updates" subtitle="Reports near Universiti Malaya" stage="T" onStage={onStage} />

      <div className="filter-pills" role="tablist" aria-label="Filter by status">
        {FILTERS.map((f) => {
          const count = f.statuses ? reports.filter((r) => f.statuses!.includes(r.status)).length : reports.length
          return (
            <button
              key={f.id}
              type="button"
              role="tab"
              aria-selected={filter === f.id}
              className={filter === f.id ? 'is-active' : ''}
              onClick={() => setFilter(f.id)}
            >
              {f.label} <span className="filter-pills__count">{count}</span>
            </button>
          )
        })}
      </div>

      {reports.length === 0 ? (
        <div className="empty-state">
          <Icon name="shoe" size={32} />
          <strong>No reports yet</strong>
          <p>Reports you submit appear here with their verification status.</p>
          <button type="button" className="btn btn--primary" onClick={onReport}>
            Report an issue
          </button>
        </div>
      ) : visible.length === 0 ? (
        <p className="empty-note">No reports with this status.</p>
      ) : (
        <ul className="report-list">
          {visible.map((report) => (
            <li key={report.id} className="report-item" style={{ borderLeftColor: statusMeta(report.status).color }}>
              <CategoryIcon category={report.category} size={24} />
              <div className="report-item__body">
                <div className="report-item__top">
                  <strong>{categoryLabel(report.category)}</strong>
                  <span className="muted small">{formatRelative(report.created_at)}</span>
                </div>
                {report.description && <p className="report-item__description">{report.description}</p>}
                <div className="report-item__meta">
                  <StatusBadge status={report.status} size="small" />
                  {durationLabel(report.category) && <span className="muted small">{durationLabel(report.category)}</span>}
                  <button type="button" className="link-button" onClick={() => onShowOnMap(report)}>
                    <Icon name="pin" size={14} /> Show on map
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="legend-card" aria-label="Status legend">
        <StatusBadge status="pending" size="small" />
        <StatusBadge status="verified_active" size="small" />
        <StatusBadge status="verified_cleared" size="small" />
        <p className="muted small">Only active obstacles change WalkLah routes.</p>
      </div>
    </div>
  )
}

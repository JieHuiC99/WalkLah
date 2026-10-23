import { useState } from 'react'
import * as api from '../../api/walklahApi'
import { CategoryIcon } from '../../components/CategoryIcon'
import { Icon } from '../../components/icons'
import { ReportPhoto, SampleTag } from '../../components/ReportPhoto'
import { StatusBadge } from '../../components/StatusBadge'
import { categoryLabel } from '../../config/categories'
import { statusMeta } from '../../config/status'
import type { LatLon, Report, ReportStatus } from '../../types'
import { formatRelative } from '../../utils/format'
import { newestFirst } from '../../utils/reports'
import { t } from '../i18n'
import { deviceId, distanceLabel } from '../lib'
import { haversine } from '../walk'

type Filter = 'open' | 'active' | 'pending' | 'closed'

const NEARBY_M = 10_000

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
  return hours >= 1
    ? t('Expires in {h} h unless reconfirmed', { h: hours })
    : t('Expires within the hour unless reconfirmed')
}

interface Props {
  reports: Report[]
  /** Map centre or the walker's position: nearby reports first. */
  near: LatLon | null
  onChanged: () => Promise<void>
  onShowOnMap: (report: Report) => void
  onReport: () => void
}

export function CommunityScreen({ reports, near, onChanged, onShowOnMap, onReport }: Props) {
  const [filter, setFilter] = useState<Filter>('open')
  const [scope, setScope] = useState<'nearby' | 'all'>('nearby')
  const [busy, setBusy] = useState<string | null>(null)
  const [voted, setVoted] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<{ id: string; message: string } | null>(null)
  const active = FILTERS.find((f) => f.id === filter)!

  const distanceTo = (r: Report) =>
    near ? haversine([near.longitude, near.latitude], [r.longitude, r.latitude]) : null
  const inScope = (r: Report) => scope === 'all' || !near || (distanceTo(r) ?? 0) <= NEARBY_M
  const scoped = reports.filter(inScope)
  const visible = (
    scope === 'nearby' && near
      ? [...scoped].sort((a, b) => (distanceTo(a) ?? 0) - (distanceTo(b) ?? 0))
      : newestFirst(scoped)
  ).filter((r) => active.statuses.includes(r.status))

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
      <h1 className="go-title">{t('Community updates')}</h1>
      <div className="segmented segmented--two community-scope" role="radiogroup" aria-label={t('Area')}>
        {(['nearby', 'all'] as const).map((s) => (
          <button key={s} type="button" role="radio" aria-checked={scope === s} className={scope === s ? 'is-active' : ''} onClick={() => setScope(s)}>
            {s === 'nearby' ? t('Within 10 km') : t('All of Malaysia')}
          </button>
        ))}
      </div>

      <div className="filter-pills" role="tablist" aria-label={t('Filter by status')}>
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            role="tab"
            aria-selected={filter === f.id}
            className={filter === f.id ? 'is-active' : ''}
            onClick={() => setFilter(f.id)}
          >
            {t(f.label)} <span className="filter-pills__count">{scoped.filter((r) => f.statuses.includes(r.status)).length}</span>
          </button>
        ))}
      </div>

      {scoped.length === 0 ? (
        <div className="empty-state">
          <Icon name="shoe" size={32} />
          <strong>{t('No reports here yet')}</strong>
          <p>{t('Seen a blocked path, flooding or a broken light? Let the next walker know.')}</p>
          <button type="button" className="btn btn--primary" onClick={onReport}>
            {t('Report an issue')}
          </button>
        </div>
      ) : visible.length === 0 ? (
        <p className="empty-note">{t('Nothing here right now.')}</p>
      ) : (
        <ul className="report-list">
          {visible.map((report) => {
            const open = report.status === 'pending' || report.status === 'verified_active'
            const myVote = voted[report.id]
            const expiry = expiresIn(report)
            const distance = distanceTo(report)
            return (
              <li key={report.id} className="report-item" style={{ borderLeftColor: statusMeta(report.status).color }}>
                <CategoryIcon category={report.category} size={22} />
                <div className="report-item__body">
                  <div className="report-item__top">
                    <strong>{t(categoryLabel(report.category))}</strong>
                    <span className="muted small">
                      {distance !== null ? `${distanceLabel(distance)} · ` : ''}
                      {formatRelative(report.created_at)}
                    </span>
                  </div>
                  {report.description && <p className="report-item__description">{report.description}</p>}
                  <ReportPhoto report={report} />
                  <div className="report-item__meta">
                    <StatusBadge status={report.status} size="small" />
                    {report.source === 'sample' && <SampleTag />}
                    {report.community_confirmed && (
                      <span className="status-badge status-badge--amber status-badge--small">{t('Confirmed by walkers')}</span>
                    )}
                    {report.source === 'operator' && <span className="muted small">{t('Official update')}</span>}
                    <button type="button" className="link-button" onClick={() => onShowOnMap(report)}>
                      <Icon name="pin" size={14} /> {t('Map')}
                    </button>
                  </div>
                  {(report.confirmations.still_there > 0 || report.confirmations.cleared > 0) && (
                    <p className="muted small">
                      {t('{a} still there · {b} say cleared', {
                        a: report.confirmations.still_there,
                        b: report.confirmations.cleared,
                      })}
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
                        {t('Still there')}
                      </button>
                      <button
                        type="button"
                        className={`vote vote--cleared${myVote === false ? ' is-mine' : ''}`}
                        disabled={busy === report.id}
                        onClick={() => void vote(report, false)}
                      >
                        {t('Cleared')}
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
        {t(
          'When 3 or more walkers confirm a temporary hazard, Practical and Enjoyable routes avoid it until an operator checks it. Operator-verified obstacles are always avoided.',
        )}
      </p>
    </div>
  )
}

import { useEffect, useState } from 'react'
import * as api from '../../api/walklahApi'
import { Icon } from '../../components/icons'
import type { FeedbackRow } from '../../types'
import { formatRelative, formatSigned } from '../../utils/format'
import type { StageProps } from '../InsightsApp'
import { Sparkline } from '../Sparkline'
import { StageHeader } from './StageHeader'

export function ExploreStage({ operatorKey, overview, bbox, trends }: StageProps) {
  const [feedback, setFeedback] = useState<FeedbackRow[]>([])
  useEffect(() => {
    let cancelled = false
    api.getFeedback(operatorKey, bbox).then((rows) => !cancelled && setFeedback(rows), () => undefined)
    return () => {
      cancelled = true
    }
  }, [operatorKey, bbox])

  const e = overview?.explore
  const answered = e ? e.feedback.yes + e.feedback.partly + e.feedback.no : 0
  return (
    <div className="stage">
      <StageHeader letter="E" title="Explore" lead="How walkers use the routes — from walkers who opted in to anonymous statistics." />

      {e && e.route_requests_30d === 0 ? (
        <p className="empty-note">
          No opted-in route requests in this area yet. In the walker view, walkers can turn on "Share anonymous route stats" in How WalkLah works.
        </p>
      ) : null}

      {e && (
        <div className="tile-grid">
          <div className="tile">
            <span className="tile__value">{e.route_requests_30d}</span>
            <span className="tile__label">Route comparisons (30 days)</span>
          </div>
          <div className={`tile${e.requests_hitting_barriers > 0 ? ' tile--alert' : ''}`}>
            <span className="tile__value">{e.requests_hitting_barriers}</span>
            <span className="tile__label">Hit a verified barrier</span>
          </div>
          <div className="tile">
            <span className="tile__value">{Math.round(e.detour_m_caused_by_barriers).toLocaleString('en-MY')} m</span>
            <span className="tile__label">Extra walking caused by barriers</span>
          </div>
          <div className="tile">
            <span className="tile__value">
              {e.average_shade_gain_pct === null ? '—' : formatSigned(e.average_shade_gain_pct, 'pts')}
            </span>
            <span className="tile__label">Shade on Enjoyable vs Shortest routes (daytime average)</span>
          </div>
        </div>
      )}

      {trends && (
        <div className="sparkline-row">
          <Sparkline label="Route comparisons" values={trends.series.route_comparisons} weeks={trends.weeks} />
        </div>
      )}

      <section className="card">
        <h2>After-walk feedback</h2>
        <p className="muted small">Was the recommended route passable? This is how WalkLah's advice gets checked against reality.</p>
        {answered === 0 ? (
          <p className="empty-note">No feedback yet.</p>
        ) : (
          <>
            <div className="feedback-bar" aria-label="Feedback split">
              {(['yes', 'partly', 'no'] as const).map((k) => (
                <span key={k} className={`feedback-bar__${k}`} style={{ flex: e!.feedback[k] }}>
                  {e!.feedback[k] > 0 ? `${{ yes: 'Passable', partly: 'Partly', no: 'Not passable' }[k]} ${e!.feedback[k]}` : ''}
                </span>
              ))}
            </div>
            <ul className="feedback-list">
              {feedback.slice(0, 8).map((f, i) => (
                <li key={i}>
                  <strong>{{ yes: 'Passable', partly: 'Partly passable', no: 'Not passable' }[f.passable]}</strong>
                  <span className="muted small">
                    {f.mode} route · {formatRelative(f.time)}
                  </span>
                  {f.note && <p>{f.note}</p>}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <p className="muted small">
        <Icon name="lock" size={14} /> {e?.consent_note ?? 'Only opted-in, anonymous statistics are shown.'} Kept 30 days.
      </p>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { categoryLabel } from '../config/categories'
import { statusMeta } from '../config/status'
import type { Overview, ScenarioResult, Trends } from '../types'
import { photoSrc } from '../utils/photo'
import { formatMetres } from '../utils/format'

/** Township summary shown only when printing (Print report → Save as PDF). */
export function PrintReport({
  overview,
  trends,
  scenario,
  bbox,
}: {
  overview: Overview | null
  trends: Trends | null
  scenario: ScenarioResult | null
  bbox: string | null
}) {
  // The time printed on the report is when Print was pressed.
  const [printedAt, setPrintedAt] = useState(() => new Date())
  useEffect(() => {
    const onBeforePrint = () => setPrintedAt(new Date())
    window.addEventListener('beforeprint', onBeforePrint)
    return () => window.removeEventListener('beforeprint', onBeforePrint)
  }, [])
  if (!overview) return null
  const t = overview.track
  const e = overview.explore
  const c = overview.survey.coverage
  const sum = (values: number[] | undefined) => (values ?? []).reduce((a, b) => a + b, 0)
  return (
    <section className="print-report" aria-hidden="true">
      <header>
        <h1>WalkLah township walking report</h1>
        <p>
          {bbox ? `Area: ${bbox.split(',').map(Number).map((v) => v.toFixed(3)).join(', ')} (west, south, east, north)` : 'Area: all of Malaysia'}
          {' · '}
          {printedAt.toLocaleString('en-MY', { dateStyle: 'long', timeStyle: 'short' })}
        </p>
      </header>

      <h2>Track — reports</h2>
      <table>
        <tbody>
          <tr>
            <th>Open reports</th>
            <td>{(t.reports_by_status.pending ?? 0) + (t.reports_by_status.verified_active ?? 0)}</td>
            <th>Verified active</th>
            <td>{t.reports_by_status.verified_active ?? 0}</td>
          </tr>
          <tr>
            <th>Confirmed by walkers</th>
            <td>{t.community_confirmed}</td>
            <th>Official closures</th>
            <td>{t.operator_closures}</td>
          </tr>
          <tr>
            <th>Reported (8 weeks)</th>
            <td>{sum(trends?.series.reports)}</td>
            <th>Resolved (8 weeks)</th>
            <td>{sum(trends?.series.resolved)}</td>
          </tr>
        </tbody>
      </table>

      <h2>Explore — opted-in trips (30 days)</h2>
      <table>
        <tbody>
          <tr>
            <th>Route comparisons</th>
            <td>{e.route_requests_30d}</td>
            <th>Met a verified barrier</th>
            <td>{e.requests_hitting_barriers}</td>
          </tr>
          <tr>
            <th>Extra walking from barriers</th>
            <td>{formatMetres(e.detour_m_caused_by_barriers)}</td>
            <th>After-walk feedback</th>
            <td>
              {e.feedback.yes} passable · {e.feedback.partly} partly · {e.feedback.no} not
            </td>
          </tr>
        </tbody>
      </table>

      <h2>Prioritise — top issues</h2>
      {overview.prioritise.top_issues.length === 0 ? (
        <p>No open issues in this area.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Issue</th>
              <th>Status</th>
              <th>Trips affected</th>
              <th>Avg detour</th>
              <th>Votes</th>
              <th>Priority</th>
            </tr>
          </thead>
          <tbody>
            {overview.prioritise.top_issues.map((issue, i) => (
              <tr key={issue.report.id}>
                <td>{i + 1}</td>
                <td>
                  {categoryLabel(issue.report.category)}
                  {issue.path_name ? ` · ${issue.path_name}` : ''}
                  {issue.report.source === 'sample' ? ' (sample)' : ''}
                  {issue.report.photo_url && (
                    <img className="print-report__photo" src={photoSrc(issue.report.photo_url)!} alt="" />
                  )}
                </td>
                <td>{statusMeta(issue.report.status).label}</td>
                <td>{issue.trips_affected}</td>
                <td>{formatMetres(issue.average_detour_m)}</td>
                <td>{issue.still_there_votes}</td>
                <td>{issue.priority}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="print-report__note">Priority = {overview.prioritise.formula}.</p>

      {scenario && (
        <>
          <h2>Planning scenario — not built</h2>
          <p>
            {scenario.label}: {scenario.pairs_improved} of {scenario.pairs_checked} place pairs get shorter,{' '}
            {formatMetres(scenario.total_saved_m)} saved in total
            {scenario.cost?.rm_per_metre_saved
              ? `; RM ${scenario.cost.rm_per_metre_saved.toLocaleString('en-MY')} per metre saved (operator's estimate)`
              : ''}
            .
          </p>
        </>
      )}

      <h2>Survey — what the data covers</h2>
      <p>
        {c.network_km.toLocaleString('en-MY')} km of mapped walking paths · sidewalk status known on{' '}
        {Math.round(c.sidewalk_known_pct)}% · {c.audited_segments ?? 0} path segments checked on foot by the team.
      </p>
      <p className="print-report__note">
        Sources: {overview.survey.sources.join(' · ')}. Comfort estimates, not safety guarantees.
      </p>
    </section>
  )
}

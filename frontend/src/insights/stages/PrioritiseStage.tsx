import { useEffect, useState } from 'react'
import * as api from '../../api/walklahApi'
import { CategoryIcon } from '../../components/CategoryIcon'
import { Icon } from '../../components/icons'
import { StatusBadge } from '../../components/StatusBadge'
import { categoryLabel } from '../../config/categories'
import type { BarrierCandidate, Issue, ScenarioResult } from '../../types'
import { formatMetres } from '../../utils/format'
import type { StageProps } from '../InsightsApp'
import { StageHeader } from './StageHeader'

export function PrioritiseStage({ operatorKey, reports, flyTo, startPick, pick, picked, clearPicked }: StageProps) {
  const [issues, setIssues] = useState<Issue[] | null>(null)
  const [formula, setFormula] = useState('')
  const [candidates, setCandidates] = useState<BarrierCandidate[]>([])

  // Re-rank whenever the reports change.
  useEffect(() => {
    let cancelled = false
    Promise.all([api.getIssues(operatorKey), api.getBarrierCandidates(operatorKey)]).then(
      ([ranked, barriers]) => {
        if (cancelled) return
        setIssues(ranked.issues)
        setFormula(ranked.formula)
        setCandidates(barriers)
      },
      () => undefined,
    )
    return () => {
      cancelled = true
    }
  }, [operatorKey, reports])

  return (
    <div className="stage">
      <StageHeader letter="P" title="Prioritise" lead="Which problems cost walkers the most, and what a fix would change." />

      <section className="card">
        <h2>Ranked issues</h2>
        {issues === null ? (
          <p className="muted">Loading…</p>
        ) : issues.length === 0 ? (
          <p className="empty-note">No open issues. Verified and pending reports are ranked here.</p>
        ) : (
          <ol className="issue-list">
            {issues.map((issue, i) => (
              <li key={issue.report.id}>
                <span className="issue-list__rank">{i + 1}</span>
                <CategoryIcon category={issue.report.category} size={18} />
                <div className="issue-list__text">
                  <strong>
                    {categoryLabel(issue.report.category)}
                    {issue.path_name ? ` · ${issue.path_name}` : ''}
                  </strong>
                  <span className="muted small">
                    {issue.trips_affected} trips affected · avg detour {Math.round(issue.average_detour_m)} m ·{' '}
                    {issue.still_there_votes} still-there votes
                  </span>
                </div>
                <StatusBadge status={issue.report.status} size="small" />
                <span className="issue-list__score" title="Priority score">
                  {issue.priority}
                </span>
                <button type="button" className="icon-btn" aria-label="Show on map" onClick={() => flyTo(issue.report)}>
                  <Icon name="pin" size={16} />
                </button>
              </li>
            ))}
          </ol>
        )}
        {formula && <p className="muted small">Priority = {formula}.</p>}
      </section>

      <ScenarioTool
        operatorKey={operatorKey}
        candidates={candidates}
        picking={pick}
        start={picked.linkStart}
        end={picked.linkEnd}
        onPickLink={() => {
          clearPicked()
          startPick({ purpose: 'link-start' })
        }}
        onClearLink={clearPicked}
        flyTo={flyTo}
      />
    </div>
  )
}

function ScenarioTool({
  operatorKey,
  candidates,
  picking,
  start,
  end,
  onPickLink,
  onClearLink,
  flyTo,
}: {
  operatorKey: string
  candidates: BarrierCandidate[]
  picking: StageProps['pick']
  start: StageProps['picked']['linkStart']
  end: StageProps['picked']['linkEnd']
  onPickLink: () => void
  onClearLink: () => void
  flyTo: StageProps['flyTo']
}) {
  const [type, setType] = useState<'remove_barrier' | 'add_link'>(candidates.length ? 'remove_barrier' : 'add_link')
  const [barrier, setBarrier] = useState<string>('')
  const [label, setLabel] = useState('')
  const [result, setResult] = useState<ScenarioResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const chosenBarrier = barrier || candidates[0]?.segment_id || ''

  const run = async () => {
    setError(null)
    setRunning(true)
    try {
      const body =
        type === 'remove_barrier'
          ? { type, segment_id: chosenBarrier, label: label || undefined }
          : { type, start: start!, end: end!, label: label || undefined }
      setResult(await api.evaluateScenario(operatorKey, body))
    } catch (e) {
      setError(api.errorMessage(e))
    } finally {
      setRunning(false)
    }
  }

  const ready = type === 'remove_barrier' ? Boolean(chosenBarrier) : Boolean(start && end)
  return (
    <section className="card scenario">
      <h2>
        Intervention scenario <span className="hypo-tag">Hypothetical</span>
      </h2>
      <p className="muted small">
        Test a fix on a copy of the walking network and see the distance saved between the station, bus stops and key
        destinations. The live map never changes.
      </p>
      <div className="segmented" role="radiogroup" aria-label="Scenario type">
        <button
          type="button"
          role="radio"
          aria-checked={type === 'remove_barrier'}
          className={type === 'remove_barrier' ? 'is-active' : ''}
          onClick={() => setType('remove_barrier')}
        >
          Fix a verified barrier
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={type === 'add_link'}
          className={type === 'add_link' ? 'is-active' : ''}
          onClick={() => setType('add_link')}
        >
          Add a new walkway
        </button>
      </div>

      {type === 'remove_barrier' ? (
        candidates.length === 0 ? (
          <p className="empty-note">No verified barriers right now. Verify one in Track, or try "Add a new walkway".</p>
        ) : (
          <select className="text-input" value={chosenBarrier} onChange={(e) => setBarrier(e.target.value)}>
            {candidates.map((c) => (
              <option key={c.segment_id} value={c.segment_id}>
                {categoryLabel(c.category)}
                {c.path_name ? ` · ${c.path_name}` : ''} ({c.report_id})
              </option>
            ))}
          </select>
        )
      ) : (
        <div className="link-picker">
          <button type="button" className={`btn btn--small${picking ? ' btn--dark' : ''}`} onClick={onPickLink}>
            <Icon name="plus" size={16} /> {start ? 'Redraw on map' : 'Draw on map'}
          </button>
          <span className="muted small">
            {start && end ? 'Walkway drawn (dashed blue line).' : start ? 'Now click where it ends.' : 'Click two points on the map.'}
          </span>
          {(start || end) && (
            <button type="button" className="link-button" onClick={onClearLink}>
              Clear
            </button>
          )}
        </div>
      )}

      <input
        className="text-input"
        placeholder="Label (optional), e.g. Covered link to LRT"
        value={label}
        maxLength={80}
        onChange={(e) => setLabel(e.target.value)}
      />
      <button type="button" className="btn btn--primary btn--small" disabled={!ready || running} onClick={() => void run()}>
        {running ? 'Calculating…' : 'Run scenario'}
      </button>
      {error && <p className="inline-error">{error}</p>}

      {result && (
        <div className="scenario-result">
          <p className="hypo-banner">
            <Icon name="info" size={16} /> Hypothetical — not built. {result.label}
            {result.link_length_m ? ` (${Math.round(result.link_length_m)} m)` : ''}
          </p>
          <div className="tile-grid tile-grid--three">
            <div className="tile">
              <span className="tile__value">{result.pairs_improved}</span>
              <span className="tile__label">of {result.pairs_checked} place pairs get shorter</span>
            </div>
            <div className="tile">
              <span className="tile__value">{formatMetres(result.total_saved_m)}</span>
              <span className="tile__label">walking saved across those pairs</span>
            </div>
            <div className="tile">
              <span className="tile__value">{result.newly_connected}</span>
              <span className="tile__label">pairs newly connected</span>
            </div>
          </div>
          {result.pairs_improved > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>From</th>
                  <th>To</th>
                  <th>Before</th>
                  <th>After</th>
                  <th>Saved</th>
                </tr>
              </thead>
              <tbody>
                {result.rows
                  .filter((r) => (r.saved_m ?? 0) > 1 || r.newly_connected)
                  .slice(0, 10)
                  .map((r) => (
                    <tr key={`${r.from}-${r.to}`}>
                      <td>{r.from}</td>
                      <td>{r.to}</td>
                      <td>{r.before_m === null ? 'no route' : formatMetres(r.before_m)}</td>
                      <td>{r.after_m === null ? '—' : formatMetres(r.after_m)}</td>
                      <td className="saved">{r.newly_connected ? 'new' : formatMetres(r.saved_m ?? 0)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
          <ul className="assumption-list">
            {result.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
          {type === 'remove_barrier' && candidates.find((c) => c.segment_id === chosenBarrier) && (
            <button
              type="button"
              className="link-button"
              onClick={() => flyTo(candidates.find((c) => c.segment_id === chosenBarrier)!)}
            >
              <Icon name="pin" size={14} /> Show barrier on map
            </button>
          )}
        </div>
      )}
    </section>
  )
}

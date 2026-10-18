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

export function PrioritiseStage({ operatorKey, reports, bbox, flyTo, startPick, pick, picked, clearPicked, onScenario }: StageProps) {
  const [issues, setIssues] = useState<Issue[] | null>(null)
  const [formula, setFormula] = useState('')
  const [candidates, setCandidates] = useState<BarrierCandidate[]>([])

  // Re-rank whenever the reports change.
  useEffect(() => {
    let cancelled = false
    Promise.all([api.getIssues(operatorKey, bbox), api.getBarrierCandidates(operatorKey, bbox)]).then(
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
  }, [operatorKey, reports, bbox])

  return (
    <div className="stage">
      <StageHeader letter="P" title="Prioritise" lead="Which problems cost walkers the most, and what a fix would change." />

      <section className="card">
        <h2>Ranked issues</h2>
        {issues === null ? (
          <p className="muted">Loading…</p>
        ) : issues.length === 0 ? (
          <p className="empty-note">No open issues in this area. Verified and pending reports are ranked here.</p>
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
        onResult={onScenario}
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
  onResult,
}: {
  operatorKey: string
  candidates: BarrierCandidate[]
  picking: StageProps['pick']
  start: StageProps['picked']['linkStart']
  end: StageProps['picked']['linkEnd']
  onPickLink: () => void
  onClearLink: () => void
  flyTo: StageProps['flyTo']
  onResult: (result: ScenarioResult | null) => void
}) {
  const [type, setType] = useState<'remove_barrier' | 'add_link'>('remove_barrier')
  const [barrier, setBarrier] = useState<string>('')
  const [label, setLabel] = useState('')
  const [cost, setCost] = useState('')
  const [result, setResult] = useState<ScenarioResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const chosenBarrier = barrier || candidates[0]?.segment_id || ''

  const run = async () => {
    setError(null)
    setRunning(true)
    try {
      const costRm = Number(cost.replace(/[^0-9.]/g, ''))
      const extra = { label: label || undefined, cost_rm: costRm > 0 ? costRm : undefined }
      const body =
        type === 'remove_barrier'
          ? { type, segment_id: chosenBarrier, ...extra }
          : { type, start: start!, end: end!, ...extra }
      const next = await api.evaluateScenario(operatorKey, body)
      setResult(next)
      onResult(next)
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
        Intervention scenario <span className="hypo-tag">Planning only</span>
      </h2>
      <p className="muted small">
        Test a fix on a copy of the walking network and see the distance saved between the stations, bus stops and
        everyday destinations around it. The live map never changes.
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
      <label className="cost-field">
        <span className="muted small">Estimated cost of the works (optional)</span>
        <span className="cost-field__input">
          <span>RM</span>
          <input
            className="text-input"
            inputMode="decimal"
            placeholder="e.g. 45,000"
            value={cost}
            onChange={(e) => setCost(e.target.value)}
          />
        </span>
      </label>
      <button type="button" className="btn btn--primary btn--small" disabled={!ready || running} onClick={() => void run()}>
        {running ? 'Calculating…' : 'Run scenario'}
      </button>
      {error && <p className="inline-error">{error}</p>}

      {result && (
        <div className="scenario-result">
          <p className="hypo-banner">
            <Icon name="info" size={16} /> Planning scenario — not built. {result.label}
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
          {result.cost && (
            <div className="tile-grid tile-grid--two">
              <div className="tile">
                <span className="tile__value">
                  {result.cost.rm_per_metre_saved === null
                    ? '—'
                    : `RM ${result.cost.rm_per_metre_saved.toLocaleString('en-MY')}`}
                </span>
                <span className="tile__label">per metre of walking saved</span>
              </div>
              <div className="tile">
                <span className="tile__value">{result.cost.metres_saved_per_rm_1000.toLocaleString('en-MY')} m</span>
                <span className="tile__label">saved per RM 1,000 ({result.cost.source.toLowerCase()})</span>
              </div>
            </div>
          )}
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

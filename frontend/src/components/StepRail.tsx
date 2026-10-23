import type { StepStage } from '../app/navigation'

const STAGES: { stage: StepStage; name: string; hint: string }[] = [
  { stage: 'S', name: 'Survey', hint: 'Map data & audits' },
  { stage: 'T', name: 'Track', hint: 'Reports & verification' },
  { stage: 'E', name: 'Explore', hint: 'How routes are used' },
  { stage: 'P', name: 'Prioritise', hint: 'What to fix first' },
]

interface Props {
  current: StepStage
  tone?: 'light' | 'dark'
  onSelect?: (stage: StepStage) => void
}

/** The S.T.E.P. pipeline as navigation for the operator view: one stage highlighted, all reachable. */
export function StepRail({ current, tone = 'light', onSelect }: Props) {
  return (
    <ol className={`step-rail step-rail--${tone}`} aria-label="S.T.E.P. stages">
      {STAGES.map((s) => {
        const state = s.stage === current ? 'current' : 'todo'
        const content = (
          <>
            <span className="step-rail__dot">{s.stage}</span>
            <span className="step-rail__name">{s.name}</span>
            <span className="step-rail__hint">{s.hint}</span>
          </>
        )
        return (
          <li key={s.stage} className={`step-rail__step is-${state}`} aria-current={state === 'current' ? 'step' : undefined}>
            {onSelect ? (
              <button type="button" className="step-rail__button" onClick={() => onSelect(s.stage)}>
                {content}
              </button>
            ) : (
              content
            )}
          </li>
        )
      })}
    </ol>
  )
}

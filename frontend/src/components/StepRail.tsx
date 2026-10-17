import type { StepStage } from '../app/navigation'
import { Icon } from './icons'

const STAGES: { stage: StepStage; name: string }[] = [
  { stage: 'S', name: 'Survey' },
  { stage: 'T', name: 'Track' },
  { stage: 'E', name: 'Explore' },
  { stage: 'P', name: 'Prioritise' },
]

interface Props {
  current: StepStage
  tone?: 'light' | 'dark'
  onSelect?: (stage: StepStage) => void
}

/** The S.T.E.P. footprint rail: current stage in yellow, earlier stages marked with a footprint. */
export function StepRail({ current, tone = 'light', onSelect }: Props) {
  const currentIndex = STAGES.findIndex((s) => s.stage === current)
  return (
    <ol className={`step-rail step-rail--${tone}`} aria-label="S.T.E.P. framework">
      {STAGES.map((s, index) => {
        const state = index === currentIndex ? 'current' : index < currentIndex ? 'done' : 'todo'
        const content = (
          <>
            <span className="step-rail__dot">{state === 'done' ? <Icon name="shoe" size={14} /> : s.stage}</span>
            <span className="step-rail__name">{s.name}</span>
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

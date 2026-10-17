import type { ReactNode } from 'react'
import type { StepStage } from '../app/navigation'
import { StepRail } from './StepRail'

interface Props {
  title: string
  subtitle?: ReactNode
  stage: StepStage
  onStage?: (stage: StepStage) => void
  tone?: 'light' | 'dark'
  actions?: ReactNode
}

const STAGE_NAMES: Record<StepStage, string> = { S: 'Survey', T: 'Track', E: 'Explore', P: 'Prioritise' }

export function ScreenHeader({ title, subtitle, stage, onStage, tone = 'light', actions }: Props) {
  return (
    <header className={`screen-header screen-header--${tone}`}>
      <div className="screen-header__top">
        <div>
          <span className="stage-tag">
            {stage} · {STAGE_NAMES[stage]}
          </span>
          <h1 className="screen-header__title">{title}</h1>
          {subtitle && <p className="screen-header__subtitle">{subtitle}</p>}
        </div>
        {actions}
      </div>
      <StepRail current={stage} tone={tone} onSelect={onStage} />
    </header>
  )
}

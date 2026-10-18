import { Icon } from '../components/icons'
import type { Endpoint } from './types'

interface Props {
  from: Endpoint | null
  to: Endpoint | null
  onOpenPicker: (which: 'from' | 'to') => void
  onSwap: () => void
  compact?: boolean
}

/** Start / destination card. Each field opens the location picker (search, your location, map pin). */
export function TripCard({ from, to, onOpenPicker, onSwap, compact = false }: Props) {
  if (compact) {
    return (
      <div className="trip-line">
        <button type="button" className="trip-line__end" onClick={() => onOpenPicker('from')}>
          <span className="trip-card__origin" aria-hidden="true" />
          <span className={from ? '' : 'is-empty'}>{from?.label ?? 'Start'}</span>
        </button>
        <Icon name="arrowRight" size={14} className="trip-line__arrow" />
        <button type="button" className="trip-line__end" onClick={() => onOpenPicker('to')}>
          <Icon name="pin" size={14} className="trip-card__dest" />
          <span className={to ? '' : 'is-empty'}>{to?.label ?? 'Destination'}</span>
        </button>
        <button type="button" className="icon-btn icon-btn--soft trip-line__swap" onClick={onSwap} aria-label="Swap start and destination">
          <Icon name="swap" size={16} />
        </button>
      </div>
    )
  }
  return (
    <div className="trip-card">
      <div className="trip-card__markers" aria-hidden="true">
        <span className="trip-card__origin" />
        <span className="trip-card__dots" />
        <Icon name="pin" size={16} className="trip-card__dest" />
      </div>
      <div className="trip-card__fields">
        <button type="button" className="trip-card__field" onClick={() => onOpenPicker('from')}>
          <span className="trip-card__label">From</span>
          <span className={`trip-card__value${from ? '' : ' is-empty'}`}>{from?.label ?? 'Choose a start'}</span>
        </button>
        <button type="button" className="trip-card__field" onClick={() => onOpenPicker('to')}>
          <span className="trip-card__label">To</span>
          <span className={`trip-card__value${to ? '' : ' is-empty'}`}>{to?.label ?? 'Where are you walking to?'}</span>
        </button>
      </div>
      <button
        type="button"
        className="icon-btn icon-btn--soft"
        onClick={onSwap}
        disabled={!from && !to}
        aria-label="Swap start and destination"
      >
        <Icon name="swap" size={18} />
      </button>
    </div>
  )
}

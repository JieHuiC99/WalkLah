import type { Destination } from '../types'
import { Icon } from './icons'

interface Props {
  destinations: Destination[]
  from: string | null
  to: string | null
  onFromChange: (id: string | null) => void
  onToChange: (id: string | null) => void
  onSwap: () => void
  compact?: boolean
}

/** From/To selector card. Places always come from GET /destinations; the same place can't be picked twice. */
export function TripCard({ destinations, from, to, onFromChange, onToChange, onSwap, compact = false }: Props) {
  const disabled = destinations.length === 0
  return (
    <div className={`trip-card${compact ? ' trip-card--compact' : ''}`}>
      <div className="trip-card__markers" aria-hidden="true">
        <span className="trip-card__origin" />
        <span className="trip-card__dots" />
        <Icon name="pin" size={16} className="trip-card__dest" />
      </div>
      <div className="trip-card__fields">
        <label className="trip-card__field">
          <span className="trip-card__label">From</span>
          <select value={from ?? ''} disabled={disabled} onChange={(e) => onFromChange(e.target.value || null)}>
            <option value="">{disabled ? 'Loading places…' : 'Choose a start'}</option>
            {destinations.map((d) => (
              <option key={d.id} value={d.id} disabled={d.id === to}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label className="trip-card__field">
          <span className="trip-card__label">To</span>
          <select value={to ?? ''} disabled={disabled} onChange={(e) => onToChange(e.target.value || null)}>
            <option value="">{disabled ? 'Loading places…' : 'Choose a destination'}</option>
            {destinations.map((d) => (
              <option key={d.id} value={d.id} disabled={d.id === from}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button type="button" className="icon-btn icon-btn--soft" onClick={onSwap} disabled={!from && !to} aria-label="Swap start and destination">
        <Icon name="swap" size={18} />
      </button>
    </div>
  )
}

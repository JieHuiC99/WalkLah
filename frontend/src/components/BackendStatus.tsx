import { Icon } from './icons'

export type BackendState = 'checking' | 'online' | 'offline'

interface Props {
  state: BackendState
  message: string | null
  onRetry: () => void
}

/** Banner shown whenever the WalkLah API can't be reached; never a blank screen. */
export function BackendStatus({ state, message, onRetry }: Props) {
  if (state === 'online') return null
  if (state === 'checking') {
    return (
      <div className="backend-status backend-status--checking" role="status">
        <span className="spinner" aria-hidden="true" /> Connecting to the WalkLah server…
      </div>
    )
  }
  return (
    <div className="backend-status backend-status--offline" role="alert">
      <Icon name="alert" size={18} />
      <span className="backend-status__text">{message ?? "Can't reach the WalkLah server."}</span>
      <button type="button" className="btn btn--small btn--light" onClick={onRetry}>
        <Icon name="refresh" size={16} /> Retry
      </button>
    </div>
  )
}

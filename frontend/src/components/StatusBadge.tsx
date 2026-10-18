import { statusMeta } from '../config/status'
import { t } from '../go/i18n'
import { Icon } from './icons'

/** Status pill: colour, icon and text label together, never colour alone. */
export function StatusBadge({ status, size = 'normal' }: { status: string; size?: 'normal' | 'small' }) {
  const meta = statusMeta(status)
  return (
    <span className={`status-badge status-badge--${meta.tone} status-badge--${size}`}>
      <Icon name={meta.icon} size={size === 'small' ? 13 : 15} />
      {t(meta.label)}
    </span>
  )
}

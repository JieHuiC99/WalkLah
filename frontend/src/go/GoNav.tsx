import { Icon, type IconName } from '../components/icons'
import { t } from './i18n'
import type { GoTab } from './types'

const ITEMS: { tab: GoTab; label: string; icon: IconName }[] = [
  { tab: 'home', label: 'Home', icon: 'home' },
  { tab: 'explore', label: 'Explore', icon: 'route' },
  { tab: 'report', label: 'Report', icon: 'flag' },
  { tab: 'community', label: 'Community', icon: 'users' },
]

/** Walker navigation only: no operator screens in the walker view. */
export function GoNav({ active, onChange }: { active: GoTab; onChange: (tab: GoTab) => void }) {
  return (
    <nav className="bottom-nav go-nav" aria-label="Main">
      {ITEMS.map((item) => (
        <button
          key={item.tab}
          type="button"
          className={`bottom-nav__item${item.tab === active ? ' is-active' : ''}`}
          aria-current={item.tab === active ? 'page' : undefined}
          onClick={() => onChange(item.tab)}
        >
          <Icon name={item.icon} size={20} />
          <span>{t(item.label)}</span>
        </button>
      ))}
    </nav>
  )
}

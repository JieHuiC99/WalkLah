import type { Tab } from '../app/navigation'
import { Icon, type IconName } from './icons'

const ITEMS: { tab: Tab; label: string; icon: IconName }[] = [
  { tab: 'home', label: 'Home', icon: 'home' },
  { tab: 'explore', label: 'Explore', icon: 'route' },
  { tab: 'report', label: 'Report', icon: 'flag' },
  { tab: 'community', label: 'Community', icon: 'users' },
  { tab: 'operator', label: 'Operator', icon: 'chart' },
]

interface Props {
  active: Tab
  onChange: (tab: Tab) => void
}

export function BottomNav({ active, onChange }: Props) {
  return (
    <nav className="bottom-nav" aria-label="Main">
      {ITEMS.map((item) => (
        <button
          key={item.tab}
          type="button"
          className={`bottom-nav__item${item.tab === active ? ' is-active' : ''}`}
          aria-current={item.tab === active ? 'page' : undefined}
          onClick={() => onChange(item.tab)}
        >
          <Icon name={item.icon} size={20} />
          <span>{item.label}</span>
        </button>
      ))}
    </nav>
  )
}

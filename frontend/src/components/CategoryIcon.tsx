import { Icon, type IconName } from './icons'

const CATEGORY_ICONS: Record<string, { icon: IconName; tint: string }> = {
  blocked_walkway: { icon: 'barrier', tint: 'orange' },
  flooding: { icon: 'flood', tint: 'blue' },
  construction: { icon: 'crane', tint: 'amber' },
  missing_sidewalk: { icon: 'road', tint: 'grey' },
  inaccessible_crossing: { icon: 'crossing', tint: 'red' },
}

function categoryIcon(category: string) {
  return CATEGORY_ICONS[category] ?? { icon: 'dots' as IconName, tint: 'grey' }
}

export function CategoryIcon({ category, size = 20 }: { category: string; size?: number }) {
  const { icon, tint } = categoryIcon(category)
  return (
    <span className={`category-icon category-icon--${tint}`}>
      <Icon name={icon} size={size} />
    </span>
  )
}

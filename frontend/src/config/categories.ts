// Report categories from the WalkLah proposal (section 5). The server stores category as a
// free string, so this is the single place to change labels once the team confirms them.
// "duration" is display-only: the backend has no temporary/permanent field yet.

export type CategoryDuration = 'temporary' | 'permanent' | 'either'

export interface CategoryOption {
  value: string
  label: string
  duration: CategoryDuration
}

export const CATEGORIES: CategoryOption[] = [
  { value: 'blocked_walkway', label: 'Blocked walkway', duration: 'temporary' },
  { value: 'flooding', label: 'Flooding', duration: 'temporary' },
  { value: 'construction', label: 'Construction', duration: 'temporary' },
  { value: 'missing_sidewalk', label: 'Missing sidewalk', duration: 'permanent' },
  { value: 'inaccessible_crossing', label: 'Inaccessible crossing', duration: 'permanent' },
  { value: 'other', label: 'Other', duration: 'either' },
]

export function categoryOf(value: string): CategoryOption | undefined {
  return CATEGORIES.find((category) => category.value === value)
}

/** Unknown categories (e.g. created via /docs) fall back to a readable version of the raw value. */
export function categoryLabel(value: string): string {
  return categoryOf(value)?.label ?? value.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

export function durationLabel(value: string): string | null {
  const duration = categoryOf(value)?.duration
  if (duration === 'temporary') return 'Temporary'
  if (duration === 'permanent') return 'Permanent'
  return null
}

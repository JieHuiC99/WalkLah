import type { Report } from '../types'

/** created_at is ISO 8601 UTC, so string order equals time order. */
export function newestFirst(reports: Report[]): Report[] {
  return [...reports].sort((a, b) => b.created_at.localeCompare(a.created_at))
}

import type { IconName } from '../components/icons'
import type { ReportStatus } from '../types'

export interface StatusMeta {
  label: string
  icon: IconName
  /** Marker colour on the map. */
  color: string
  tone: 'amber' | 'red' | 'green' | 'grey'
  blocksRoutes: boolean
}

// One place for status colour + label + icon. Colour is never used without the label.
export const STATUS_META: Record<ReportStatus, StatusMeta> = {
  pending: { label: 'Pending', icon: 'clock', color: '#f0a500', tone: 'amber', blocksRoutes: false },
  verified_active: { label: 'Active obstacle', icon: 'alert', color: '#e5484d', tone: 'red', blocksRoutes: true },
  verified_cleared: { label: 'Cleared', icon: 'check', color: '#1fb574', tone: 'green', blocksRoutes: false },
  disputed: { label: 'Disputed', icon: 'info', color: '#8e887a', tone: 'grey', blocksRoutes: false },
  stale: { label: 'Stale', icon: 'clock', color: '#8e887a', tone: 'grey', blocksRoutes: false },
}

export function statusMeta(status: string): StatusMeta {
  return STATUS_META[status as ReportStatus] ?? STATUS_META.stale
}

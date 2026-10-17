// Mirrors the WalkLah backend (backend/app/schemas.py, report_store.py, routing.py).

export interface Destination {
  id: string
  name: string
  latitude: number
  longitude: number
}

export interface DestinationsResponse {
  destinations: Destination[]
}

export type RouteMode = 'baseline' | 'walklah'

export interface LineStringGeometry {
  type: 'LineString'
  /** GeoJSON order: [longitude, latitude] */
  coordinates: [number, number][]
}

export interface RouteResponse {
  route_type: RouteMode
  start_id: string
  destination_id: string
  distance_m: number
  /** Assumes 1.2 m/s, rounded to 2 decimals by the server. */
  estimated_minutes: number
  verification: string
  /** Verified-active blocked segments on the baseline path (walklah mode only). */
  affected_segment_ids: string[]
  geometry: LineStringGeometry
}

export type ReportStatus =
  | 'pending'
  | 'verified_active'
  | 'verified_cleared'
  | 'disputed'
  | 'stale'

export type VerifyStatus = Exclude<ReportStatus, 'pending'>

export interface Report {
  id: string
  segment_id: string
  /** Free string on the server; see config/categories.ts for known values. */
  category: string
  description: string | null
  status: ReportStatus
  latitude: number
  longitude: number
  /** ISO 8601 ending in Z, may include microseconds. */
  created_at: string
}

export interface ReportsResponse {
  reports: Report[]
}

/** segment_id is deliberately omitted: the server snaps the point to a footpath. */
export interface CreateReportBody {
  category: string
  description: string | null
  latitude: number
  longitude: number
}

export interface InsightsSummary {
  total_reports: number
  pending_reports: number
  active_obstacles: number
  cleared_reports: number
  affected_segments: number
}

export interface HealthResponse {
  status: string
}

/** FastAPI 422 validation item. */
export interface ValidationErrorItem {
  loc: (string | number)[]
  msg: string
  type: string
}

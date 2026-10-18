// Mirrors the WalkLah backend API v2 (docs/API_CONTRACT.md).

export interface LatLon {
  latitude: number
  longitude: number
}

export interface Destination extends LatLon {
  id: string
  name: string
}

export type PlaceCategory = 'transit' | 'campus' | 'daily' | 'leisure' | 'health' | 'other'

export interface Place extends LatLon {
  id: string
  name: string
  category: PlaceCategory
  kind: 'rail_station' | 'bus_stop' | null
}

export interface LineStringGeometry {
  type: 'LineString'
  /** GeoJSON order: [longitude, latitude] */
  coordinates: [number, number][]
}

export type RouteMode = 'shortest' | 'practical' | 'enjoyable'
export type Lit = 'yes' | 'no' | 'unknown'
export type Sidewalk = 'footpath' | 'yes' | 'no' | 'unknown'

export interface RouteSegment {
  id: string
  coordinates: [number, number][]
  length_m: number
  /** 0..1 shaded fraction at the requested time; null after dark */
  shade: number | null
  lit: Lit
  sidewalk: Sidewalk
}

export interface RouteWarning {
  type: 'unverified_report'
  report_id: string
  category: string
  segment_id: string
}

export interface PlannedRoute {
  mode: RouteMode
  available: true
  distance_m: number
  estimated_minutes: number
  geometry: LineStringGeometry
  segments: RouteSegment[]
  exposure: { shaded_m: number; sun_m: number; shade_pct: number } | null
  lighting: { lit_m: number; unlit_m: number; unknown_m: number }
  sidewalk_unknown_m: number
  busy_road_m: number
  steps_count: number
  crossings: { signalised: number; marked: number; unknown: number }
  affected_segment_ids: string[]
  warnings: RouteWarning[]
  reasons: string[]
  long_detour: boolean
}

export interface UnavailableRoute {
  mode: RouteMode
  available: false
  reason: string
}

export type RouteOption = PlannedRoute | UnavailableRoute

export interface RoutePoint extends LatLon {
  snapped: [number, number]
  snap_distance_m: number
  in_pilot_area: boolean
}

export interface Sun {
  altitude: number
  azimuth: number
  daylight: boolean
}

export interface RoutesResponse {
  start: RoutePoint
  end: RoutePoint
  at: string
  sun: Sun
  step_free: boolean
  routes: RouteOption[]
  data_notes: {
    estimated_building_height_pct: number
    lighting_known_pct: number | null
    sidewalk_known_pct: number | null
    canopy_source: string | null
  }
}

export interface Coverage {
  segments: number
  network_km: number
  sidewalk_known_pct: number
  dedicated_footpath_pct: number
  lighting_known_pct: number
  lighting_audited_segments: number
  covered_pct: number
  canopy_pct: number | null
  green_pct: number
  steps_pct: number
  buildings: number
  building_heights_real_pct: number
  places: number
  audited_segments?: number
}

export interface Pilot {
  anchor: Destination
  radius_m: number
  bounds: { south: number; west: number; north: number; east: number }
  featured: Place[]
  coverage: Coverage
  sources: string[]
  built_at: string | null
}

export type ReportStatus = 'pending' | 'verified_active' | 'verified_cleared' | 'disputed' | 'stale'
export type VerifyStatus = Exclude<ReportStatus, 'pending'>

export interface Report extends LatLon {
  id: string
  segment_id: string
  /** Free string on the server; see config/categories.ts for known values. */
  category: string
  description: string | null
  status: ReportStatus
  /** ISO 8601 ending in Z, may include microseconds. */
  created_at: string
  temporary_or_permanent: 'temporary' | 'permanent'
  expires_at: string | null
  has_photo: boolean
  source: 'community' | 'operator'
  confirmations: { still_there: number; cleared: number; last_at: string | null }
}

export interface ReportEvent {
  event_type: string
  verifier_role: string
  time: string
  evidence_reference: string | null
}

/** segment_id is optional: without it the server snaps the point to the nearest path. */
export interface CreateReportBody extends LatLon {
  category: string
  description: string | null
  segment_id?: string
}

export interface NearSegment {
  segment_id: string
  distance_m: number
  name: string | null
  highway: string
  sidewalk: Sidewalk
}

export interface SegmentCard {
  id: string
  name: string | null
  highway: string
  length_m: number
  sidewalk: Sidewalk
  steps: boolean
  traffic_stress: 'low' | 'medium' | 'high' | 'unknown'
  lighting: { status: Lit; source: 'audit' | 'osm_tag' | 'osm_lamp' | null }
  crossings: { node: number; type: 'signalised' | 'marked' | 'unknown' }[]
  covered_pct: number
  tree_canopy_pct: number
  green_pct: number
  shade_now_pct: number | null
  sun: Sun
  reports: Report[]
}

export interface InsightsSummary {
  total_reports: number
  pending_reports: number
  active_obstacles: number
  cleared_reports: number
  affected_segments: number
}

export interface Issue {
  report: Report
  path_name: string | null
  trips_affected: number
  average_detour_m: number
  still_there_votes: number
  priority: number
}

export interface Overview {
  survey: { coverage: Coverage; sources: string[]; built_at: string | null }
  track: {
    reports_by_status: Partial<Record<ReportStatus, number>>
    total_reports: number
    operator_closures: number
    still_there_votes: number
    cleared_votes: number
  }
  explore: {
    route_requests_30d: number
    requests_hitting_barriers: number
    detour_m_caused_by_barriers: number
    average_shade_gain_pct: number | null
    feedback: { yes: number; partly: number; no: number }
    consent_note: string
  }
  prioritise: { top_issues: Issue[]; formula: string }
}

export interface ScenarioRow {
  from: string
  to: string
  before_m: number | null
  after_m: number | null
  saved_m: number | null
  newly_connected: boolean
}

export interface ScenarioResult {
  hypothetical: true
  label: string
  description: string
  link_length_m: number | null
  pairs_checked: number
  pairs_improved: number
  newly_connected: number
  total_saved_m: number
  rows: ScenarioRow[]
  assumptions: string[]
  evaluated_at: string
}

export type ScenarioRequest =
  | { type: 'remove_barrier'; segment_id: string; label?: string }
  | { type: 'add_link'; start: LatLon; end: LatLon; label?: string }

export interface BarrierCandidate extends LatLon {
  segment_id: string
  report_id: string
  category: string
  path_name: string | null
}

export interface AuditRow {
  segment_id: string
  lit?: 'yes' | 'no' | null
  sidewalk?: 'yes' | 'no' | 'footpath' | null
  checked_at: string
  auditor?: string | null
  note?: string | null
}

export interface FeedbackRow {
  time: string
  mode: RouteMode
  passable: 'yes' | 'partly' | 'no'
  note: string | null
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

// Mirrors the WalkLah backend API v2 (docs/API_CONTRACT.md).

export interface LatLon {
  latitude: number
  longitude: number
}

export interface Destination extends LatLon {
  id: string
  name: string
}

export type PlaceCategory =
  | 'transit'
  | 'food'
  | 'shopping'
  | 'campus'
  | 'daily'
  | 'leisure'
  | 'health'
  | 'civic'
  | 'other'

export interface Place extends LatLon {
  id: string
  name: string
  category: PlaceCategory
  kind: 'rail_station' | 'station_entrance' | 'bus_stop' | null
  /** Neighbourhood and town, e.g. "Bandar Puteri, Puchong" (tells branches apart). */
  area?: string | null
  brand?: string | null
  source?: string
  distance_m?: number
}

export interface ReverseResult {
  name: string | null
  label: string
  area: string | null
  place: Place | null
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

export interface RouteStep {
  type: 'depart' | 'turn' | 'continue' | 'steps' | 'arrive'
  modifier: string | null
  /** English sentence; the app rebuilds it from the fields below for other languages. */
  instruction: string
  name: string | null
  /** Description of an unnamed way, e.g. "the footpath". */
  way: string | null
  /** Compass direction of the first step, e.g. "north-east". */
  direction: string | null
  distance_m: number
  /** Metres from the start where this step begins. */
  at_m: number
  location: [number, number]
}

export interface RouteAlert {
  type: 'sun' | 'unlit' | 'light_unknown' | 'uncovered' | 'steps' | 'crossing' | 'hazard'
  at_m: number
  length_m: number | null
  text: string
  location: [number, number]
  /** Report category for hazard alerts. */
  category?: string
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
  covered_m: number
  covered_pct: number
  steps: RouteStep[]
  alerts: RouteAlert[]
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

export type RainMode = 'auto' | 'on' | 'off'

export interface RouteWeather {
  rain_mode: RainMode
  rain_cover: boolean
  rain_probability: number | null
  precipitation_mm: number | null
  source: string | null
  note: string | null
}

export interface RoutesResponse {
  start: RoutePoint
  end: RoutePoint
  at: string
  sun: Sun
  step_free: boolean
  rain: { probability: number | null; forced: boolean; source: string | null } | null
  weather: RouteWeather
  routes: RouteOption[]
  data_notes: {
    estimated_building_height_pct: number
    lighting_known_pct: number | null
    sidewalk_known_pct: number | null
    canopy_source: string | null
  }
}

/** Coverage of the condition data. Nationwide numbers come from OSM tags; the audited area adds field checks. */
export interface Coverage {
  segments: number
  network_km: number
  sidewalk_known_pct: number
  dedicated_footpath_pct: number
  lighting_known_pct?: number
  lighting_tagged_pct?: number
  lighting_audited_segments?: number
  covered_pct?: number
  covered_tagged_pct?: number
  canopy_pct?: number | null
  green_pct?: number
  steps_pct?: number
  buildings: number
  building_heights_real_pct: number
  places: number
  lamps?: number
  crossings?: number
  audited_segments?: number
}

/** Map coverage (GET /pilot): Malaysia-wide, or the audited area only when the national data isn't built. */
export interface Pilot {
  coverage_area: 'malaysia' | 'pilot'
  anchor: Destination
  radius_m: number
  audited_area: { anchor: Destination; radius_m: number; label: string }
  bounds: { south: number; west: number; north: number; east: number }
  featured: Place[]
  coverage: Coverage
  audited_coverage: Coverage
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
  /** Temporary hazard confirmed by 3+ walkers: routes avoid it until an operator decides. */
  community_confirmed: boolean
  /** Only on POST /reports: true when the report was added as a vote to a nearby one. */
  merged?: boolean
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
  device?: string
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
  area: { west: number; south: number; east: number; north: number } | null
  survey: { coverage: Coverage; audited_coverage: Coverage; sources: string[]; built_at: string | null }
  track: {
    reports_by_status: Partial<Record<ReportStatus, number>>
    total_reports: number
    operator_closures: number
    community_confirmed: number
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
  cost: { cost_rm: number; rm_per_metre_saved: number | null; metres_saved_per_rm_1000: number; source: string } | null
  rows: ScenarioRow[]
  assumptions: string[]
  evaluated_at: string
}

export type ScenarioRequest =
  | { type: 'remove_barrier'; segment_id: string; label?: string; cost_rm?: number }
  | { type: 'add_link'; start: LatLon; end: LatLon; label?: string; cost_rm?: number }

export interface Trends {
  weeks: string[]
  series: { reports: number[]; resolved: number[]; route_comparisons: number[] }
}

export interface HeatResponse {
  kind: 'reports' | 'trips'
  points: (LatLon & { weight: number })[]
}

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
  cell_lat?: number | null
  cell_lon?: number | null
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

import type {
  AuditRow,
  BarrierCandidate,
  CreateReportBody,
  FeedbackRow,
  HealthResponse,
  InsightsSummary,
  Issue,
  NearSegment,
  Overview,
  Pilot,
  Place,
  Report,
  ReportEvent,
  RouteMode,
  RoutesResponse,
  ScenarioRequest,
  ScenarioResult,
  SegmentCard,
  ValidationErrorItem,
  VerifyStatus,
} from '../types'

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, '')

const DEFAULT_TIMEOUT_MS = 10_000
// The backend loads its graph and shade model lazily, so the first route request can take several seconds.
const ROUTE_TIMEOUT_MS = 30_000

/** status 0 = the request never got a response (network down or timeout). */
export class ApiError extends Error {
  readonly status: number
  readonly kind: 'http' | 'network' | 'timeout'

  constructor(status: number, message: string, kind: ApiError['kind'] = 'http') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.kind = kind
  }
}

function describeValidation(items: ValidationErrorItem[]): string {
  return items
    .map((item) => {
      const field = item.loc.filter((part) => part !== 'body' && part !== 'query').join('.')
      return field ? `${field}: ${item.msg}` : item.msg
    })
    .join('; ')
}

async function readErrorMessage(response: Response): Promise<string> {
  const text = await response.text().catch(() => '')
  try {
    const body: unknown = JSON.parse(text)
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail)) return describeValidation(detail as ValidationErrorItem[])
    }
  } catch {
    // Not JSON.
  }
  return text.trim() || response.statusText || `Request failed (${response.status})`
}

interface RequestOptions extends RequestInit {
  timeoutMs?: number
  operatorKey?: string | null
  text?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, operatorKey, text, ...init } = options
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) }
  if (init.body) headers['Content-Type'] = 'application/json'
  if (operatorKey) headers['X-Operator-Key'] = operatorKey
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers, signal: controller.signal })
  } catch {
    if (controller.signal.aborted) {
      throw new ApiError(0, `The WalkLah server took longer than ${timeoutMs / 1000} s to answer.`, 'timeout')
    }
    throw new ApiError(0, `Can't reach the WalkLah server at ${API_BASE}. Is the backend running?`, 'network')
  } finally {
    window.clearTimeout(timer)
  }
  if (!response.ok) {
    throw new ApiError(response.status, await readErrorMessage(response))
  }
  return (text ? await response.text() : await response.json()) as T
}

const json = (body: unknown) => JSON.stringify(body)

// ---- walkers (WalkLah Go) ------------------------------------------------

export const getHealth = () => request<HealthResponse>('/health', { timeoutMs: 5_000 })

export const getPilot = () => request<Pilot>('/pilot', { timeoutMs: ROUTE_TIMEOUT_MS })

export async function searchPlaces(q: string): Promise<Place[]> {
  return (await request<{ places: Place[] }>(`/places?${new URLSearchParams({ q })}`)).places
}

export interface RoutesQuery {
  start: { latitude: number; longitude: number }
  end: { latitude: number; longitude: number }
  /** 'YYYY-MM-DDTHH:MM' in Malaysia time, or omitted for now */
  at?: string
  stepFree: boolean
  shareStats: boolean
}

export function getRoutes(query: RoutesQuery): Promise<RoutesResponse> {
  const params = new URLSearchParams({
    start_lat: String(query.start.latitude),
    start_lon: String(query.start.longitude),
    end_lat: String(query.end.latitude),
    end_lon: String(query.end.longitude),
    step_free: String(query.stepFree),
    share_stats: String(query.shareStats),
  })
  if (query.at) params.set('at', query.at)
  return request<RoutesResponse>(`/routes?${params}`, { timeoutMs: ROUTE_TIMEOUT_MS })
}

export async function getReports(): Promise<Report[]> {
  return (await request<{ reports: Report[] }>('/reports')).reports
}

export const createReport = (body: CreateReportBody) =>
  request<Report>('/reports', { method: 'POST', body: json(body) })

export const confirmReport = (id: string, stillThere: boolean, device: string) =>
  request<Report>(`/reports/${encodeURIComponent(id)}/confirm`, {
    method: 'POST',
    body: json({ still_there: stillThere, device }),
  })

export async function nearSegments(lat: number, lon: number): Promise<NearSegment[]> {
  return (await request<{ segments: NearSegment[] }>(`/segments/near?lat=${lat}&lon=${lon}`)).segments
}

export const getSegment = (id: string, at?: string) =>
  request<SegmentCard>(`/segments/${encodeURIComponent(id)}${at ? `?at=${encodeURIComponent(at)}` : ''}`, {
    timeoutMs: ROUTE_TIMEOUT_MS,
  })

export const sendFeedback = (mode: RouteMode, passable: 'yes' | 'partly' | 'no', note: string | null, device: string) =>
  request<{ mode: RouteMode; passable: string }>('/feedback', {
    method: 'POST',
    body: json({ mode, passable, note, device }),
  })

export const getSummary = () => request<InsightsSummary>('/insights/summary')

// ---- operators (WalkLah Insights) ---------------------------------------

export const getOverview = (key: string) => request<Overview>('/insights/overview', { operatorKey: key })

export async function getIssues(key: string): Promise<{ issues: Issue[]; formula: string }> {
  return request('/insights/issues', { operatorKey: key })
}

export const verifyReport = (key: string, id: string, status: VerifyStatus, evidence?: string) =>
  request<Report>(`/reports/${encodeURIComponent(id)}/verify`, {
    method: 'PATCH',
    body: json({ status, evidence: evidence || null }),
    operatorKey: key,
  })

export async function getReportHistory(id: string): Promise<ReportEvent[]> {
  return (await request<{ events: ReportEvent[] }>(`/reports/${encodeURIComponent(id)}/history`)).events
}

export const createClosure = (key: string, body: CreateReportBody) =>
  request<Report>('/operator/closures', { method: 'POST', body: json(body), operatorKey: key })

export const evaluateScenario = (key: string, body: ScenarioRequest) =>
  request<ScenarioResult>('/scenarios/evaluate', {
    method: 'POST',
    body: json(body),
    operatorKey: key,
    timeoutMs: ROUTE_TIMEOUT_MS,
  })

export async function getBarrierCandidates(key: string): Promise<BarrierCandidate[]> {
  return (await request<{ barriers: BarrierCandidate[] }>('/scenarios/candidates', { operatorKey: key })).barriers
}

export async function getAudit(key: string): Promise<AuditRow[]> {
  return (await request<{ rows: AuditRow[] }>('/audit', { operatorKey: key })).rows
}

export const uploadAudit = (key: string, rows: AuditRow[]) =>
  request<{ saved: number; audited_segments: number }>('/audit', {
    method: 'POST',
    body: json({ rows }),
    operatorKey: key,
  })

export const auditTemplate = () => request<string>('/audit/template', { text: true })

export async function getFeedback(key: string): Promise<FeedbackRow[]> {
  return (await request<{ feedback: FeedbackRow[] }>('/insights/feedback', { operatorKey: key })).feedback
}

export const resetDemo = (key: string) =>
  request<{ status: string }>('/demo/reset', { method: 'POST', operatorKey: key })

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}

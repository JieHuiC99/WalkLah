import type {
  CreateReportBody,
  Destination,
  DestinationsResponse,
  HealthResponse,
  InsightsSummary,
  Report,
  ReportsResponse,
  RouteMode,
  RouteResponse,
  ValidationErrorItem,
  VerifyStatus,
} from '../types'

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, '')

const DEFAULT_TIMEOUT_MS = 10_000
// The backend loads its pedestrian graph lazily, so the first /route call can take several seconds.
const ROUTE_TIMEOUT_MS = 30_000

/** status 0 = the request never got a response (network down, CORS-blocked 500, or timeout). */
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
    // Unhandled server errors return plain text, not JSON.
  }
  return text.trim() || response.statusText || `Request failed (${response.status})`
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: init.body ? { 'Content-Type': 'application/json', ...init.headers } : init.headers,
      signal: controller.signal,
    })
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
  return (await response.json()) as T
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health', {}, 5_000)
}

export async function getDestinations(): Promise<Destination[]> {
  return (await request<DestinationsResponse>('/destinations')).destinations
}

export function getRoute(startId: string, destinationId: string, mode: RouteMode): Promise<RouteResponse> {
  const query = new URLSearchParams({ start_id: startId, destination_id: destinationId, mode })
  return request<RouteResponse>(`/route?${query}`, {}, ROUTE_TIMEOUT_MS)
}

export async function getReports(): Promise<Report[]> {
  return (await request<ReportsResponse>('/reports')).reports
}

export function createReport(body: CreateReportBody): Promise<Report> {
  return request<Report>('/reports', { method: 'POST', body: JSON.stringify(body) })
}

export function verifyReport(id: string, status: VerifyStatus): Promise<Report> {
  return request<Report>(`/reports/${encodeURIComponent(id)}/verify`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  })
}

export function getSummary(): Promise<InsightsSummary> {
  return request<InsightsSummary>('/insights/summary')
}

export function resetDemo(): Promise<{ status: string }> {
  return request<{ status: string }>('/demo/reset', { method: 'POST' })
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}

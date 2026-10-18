import { useEffect, useState } from 'react'
import * as api from '../api/walklahApi'
import type { RouteResponse } from '../types'

export interface RoutePair {
  /** Identifies which request this result answers (from, to and data version). */
  key: string
  baseline: RouteResponse | null
  walklah: RouteResponse | null
  baselineError: string | null
  walklahError: string | null
  /** True when the WalkLah route was refused with 404 although the usual path exists. */
  walklahBlocked: boolean
}

export type RoutesState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; routes: RoutePair }

const SERVER_ROUTE_ERROR = 'The server hit an error calculating this route. Try again, or pick another pair.'

async function describeFailure(error: unknown): Promise<string> {
  // Unhandled backend errors arrive without CORS headers and look like a network failure.
  // If the server still answers /health, it is up and the route calculation itself failed.
  if (error instanceof api.ApiError && error.kind === 'network') {
    const alive = await api.getHealth().then(
      () => true,
      () => false,
    )
    if (alive) return SERVER_ROUTE_ERROR
  }
  return api.errorMessage(error)
}

async function loadPair(key: string, from: string, to: string): Promise<RoutePair> {
  // Both routes are requested in parallel; each can fail on its own.
  const [baseline, walklah] = await Promise.allSettled([
    api.getRoute(from, to, 'baseline'),
    api.getRoute(from, to, 'walklah'),
  ])
  const baselineError = baseline.status === 'rejected' ? await describeFailure(baseline.reason) : null
  const walklahError = walklah.status === 'rejected' ? await describeFailure(walklah.reason) : null
  const walklahBlocked =
    baseline.status === 'fulfilled' &&
    walklah.status === 'rejected' &&
    walklah.reason instanceof api.ApiError &&
    walklah.reason.status === 404
  return {
    key,
    baseline: baseline.status === 'fulfilled' ? baseline.value : null,
    walklah: walklah.status === 'fulfilled' ? walklah.value : null,
    baselineError,
    walklahError,
    walklahBlocked,
  }
}

/** Fetches baseline + WalkLah routes whenever the pair or the shared data version changes. */
export function useRoutes(from: string | null, to: string | null, dataVersion: number, enabled: boolean): RoutesState {
  const key = from && to && from !== to && enabled ? `${from}|${to}|${dataVersion}` : null
  const [result, setResult] = useState<RoutePair | null>(null)

  useEffect(() => {
    if (!key || !from || !to) return
    let cancelled = false
    loadPair(key, from, to).then((pair) => {
      if (!cancelled) setResult(pair)
    })
    return () => {
      cancelled = true
    }
  }, [key, from, to])

  if (!key) return { status: 'idle' }
  // Keep showing the previous pair's lines while a refresh for the same pair is in flight.
  if (!result || result.key !== key) {
    return result && result.key.startsWith(`${from}|${to}|`) ? { status: 'ready', routes: result } : { status: 'loading' }
  }
  return { status: 'ready', routes: result }
}

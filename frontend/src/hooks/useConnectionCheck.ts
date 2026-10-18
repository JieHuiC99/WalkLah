import { useCallback, useRef, useState } from 'react'
import * as api from '../api/walklahApi'
import type { Destination } from '../types'

export interface ConnectionResult {
  fromId: string
  toId: string
  baselineMetres: number
  walklahMetres: number | null
  extraMetres: number | null
  extraMinutes: number | null
  /** Verified-active segments that the usual path between these places crosses. */
  blockedSegments: number
  noAlternative: boolean
}

export interface ConnectionCheck {
  state: 'idle' | 'running' | 'done' | 'error'
  done: number
  total: number
  results: ConnectionResult[]
  failures: number
  /** dataVersion the results were computed for. */
  version: number | null
  error: string | null
}

const IDLE: ConnectionCheck = { state: 'idle', done: 0, total: 0, results: [], failures: 0, version: null, error: null }
const CONCURRENCY = 3

/**
 * P · Prioritise: asks /route for every pair of demo places (baseline + WalkLah) and keeps
 * the pairs whose usual path is blocked by a verified obstacle. Every number comes from /route.
 */
export function useConnectionCheck() {
  const [check, setCheck] = useState<ConnectionCheck>(IDLE)
  const runId = useRef(0)

  const run = useCallback(async (destinations: Destination[], version: number) => {
    const id = ++runId.current
    const pairs: [Destination, Destination][] = []
    destinations.forEach((a, i) => destinations.slice(i + 1).forEach((b) => pairs.push([a, b])))
    setCheck({ ...IDLE, state: 'running', total: pairs.length, version })

    const results: ConnectionResult[] = []
    let failures = 0
    let done = 0
    let fatal: string | null = null
    let next = 0

    const worker = async () => {
      while (next < pairs.length && !fatal && runId.current === id) {
        const [a, b] = pairs[next++]
        const [baseline, walklah] = await Promise.allSettled([
          api.getRoute(a.id, b.id, 'baseline'),
          api.getRoute(a.id, b.id, 'walklah'),
        ])
        if (baseline.status === 'rejected') {
          if (baseline.reason instanceof api.ApiError && baseline.reason.kind === 'network') {
            fatal = baseline.reason.message
          }
          failures++
        } else if (walklah.status === 'fulfilled') {
          const blocked = walklah.value.affected_segment_ids.length
          if (blocked > 0) {
            results.push({
              fromId: a.id,
              toId: b.id,
              baselineMetres: baseline.value.distance_m,
              walklahMetres: walklah.value.distance_m,
              extraMetres: walklah.value.distance_m - baseline.value.distance_m,
              extraMinutes: walklah.value.estimated_minutes - baseline.value.estimated_minutes,
              blockedSegments: blocked,
              noAlternative: false,
            })
          }
        } else if (walklah.reason instanceof api.ApiError && walklah.reason.status === 404) {
          results.push({
            fromId: a.id,
            toId: b.id,
            baselineMetres: baseline.value.distance_m,
            walklahMetres: null,
            extraMetres: null,
            extraMinutes: null,
            blockedSegments: 0,
            noAlternative: true,
          })
        } else {
          failures++
        }
        done++
        if (runId.current === id) setCheck((c) => ({ ...c, done }))
      }
    }

    await Promise.all(Array.from({ length: CONCURRENCY }, worker))
    if (runId.current !== id) return
    results.sort((x, y) => Number(y.noAlternative) - Number(x.noAlternative) || (y.extraMetres ?? 0) - (x.extraMetres ?? 0))
    setCheck({
      state: fatal ? 'error' : 'done',
      done,
      total: pairs.length,
      results,
      failures,
      version,
      error: fatal,
    })
  }, [])

  return { check, run }
}

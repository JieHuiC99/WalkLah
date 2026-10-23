// Geometry for walk mode: where the walker is along the route, and points along it (preview).

import type { LatLon } from '../types'

const R = 6_371_000

export function haversine(a: [number, number], b: [number, number]): number {
  const [lon1, lat1, lon2, lat2] = [a[0], a[1], b[0], b[1]].map((d) => (d * Math.PI) / 180)
  const h = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

export function bearing(a: [number, number], b: [number, number]): number {
  const [lon1, lat1, lon2, lat2] = [a[0], a[1], b[0], b[1]].map((d) => (d * Math.PI) / 180)
  const y = Math.sin(lon2 - lon1) * Math.cos(lat2)
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1)
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
}

export interface RouteLine {
  coords: [number, number][]
  /** Metres from the start to each vertex. */
  cum: number[]
  total: number
}

export function routeLine(coords: [number, number][]): RouteLine {
  const cum = [0]
  for (let i = 1; i < coords.length; i++) cum.push(cum[i - 1] + haversine(coords[i - 1], coords[i]))
  return { coords, cum, total: cum[cum.length - 1] ?? 0 }
}

export interface Progress {
  /** Metres along the route of the closest point. */
  along: number
  /** Metres from the route. */
  offset: number
}

/** Closest point on the route to `p` (local flat-earth projection; fine for walking distances). */
export function project(line: RouteLine, p: LatLon, hint = 0): Progress {
  const kx = 111_320 * Math.cos((p.latitude * Math.PI) / 180)
  const ky = 110_540
  let best: Progress = { along: 0, offset: Infinity }
  let bestScore = Infinity
  // Prefer matches at or after the last known progress (routes can double back near themselves).
  for (let i = 0; i < line.coords.length - 1; i++) {
    const [ax, ay] = [(line.coords[i][0] - p.longitude) * kx, (line.coords[i][1] - p.latitude) * ky]
    const [bx, by] = [(line.coords[i + 1][0] - p.longitude) * kx, (line.coords[i + 1][1] - p.latitude) * ky]
    const dx = bx - ax
    const dy = by - ay
    const len2 = dx * dx + dy * dy
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2))
    const offset = Math.hypot(ax + t * dx, ay + t * dy)
    const along = line.cum[i] + t * (line.cum[i + 1] - line.cum[i])
    const score = offset + (along < hint - 30 ? 25 : 0)
    if (score < bestScore) {
      bestScore = score
      best = { along, offset }
    }
  }
  return best
}

/** Position and heading at `along` metres from the start. */
export function pointAt(line: RouteLine, along: number): { point: LatLon; heading: number } {
  const d = Math.max(0, Math.min(line.total, along))
  let i = 0
  while (i < line.cum.length - 2 && line.cum[i + 1] < d) i++
  const a = line.coords[i]
  const b = line.coords[Math.min(i + 1, line.coords.length - 1)]
  const span = line.cum[i + 1] - line.cum[i] || 1
  const t = (d - line.cum[i]) / span
  return {
    point: { longitude: a[0] + (b[0] - a[0]) * t, latitude: a[1] + (b[1] - a[1]) * t },
    heading: bearing(a, b),
  }
}

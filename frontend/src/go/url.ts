// Go state lives in the query string so a shared link opens the same trip, e.g.
// ?tab=explore&from=3.114548,101.661702&fn=LRT%20Universiti&to=3.121464,101.656556&tn=Dewan%20Tunku%20Canselor&t=13

import type { RouteMode } from '../types'
import { TIME_CHOICES, type TimeChoice } from './lib'
import type { Endpoint, GoTab } from './types'

const TABS: GoTab[] = ['home', 'explore', 'report', 'community']
const MODES: RouteMode[] = ['shortest', 'practical', 'enjoyable']

function parsePoint(value: string | null, label: string | null, area: string | null): Endpoint | null {
  if (!value) return null
  const [lat, lon] = value.split(',').map(Number)
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
  return { latitude: lat, longitude: lon, label: label || 'Dropped pin', area, source: label ? 'place' : 'pin' }
}

export function readGoUrl() {
  const p = new URLSearchParams(window.location.search)
  const tab = (TABS.includes(p.get('tab') as GoTab) ? p.get('tab') : 'home') as GoTab
  const time = (TIME_CHOICES.includes(p.get('t') as TimeChoice) ? p.get('t') : 'now') as TimeChoice
  const mode = MODES.includes(p.get('mode') as RouteMode) ? (p.get('mode') as RouteMode) : null
  return {
    tab,
    from: parsePoint(p.get('from'), p.get('fn'), p.get('fa')),
    to: parsePoint(p.get('to'), p.get('tn'), p.get('ta')),
    time,
    mode,
  }
}

export function writeGoUrl(state: {
  tab: GoTab
  from: Endpoint | null
  to: Endpoint | null
  time: TimeChoice
  mode: RouteMode | null
}): void {
  const p = new URLSearchParams()
  p.set('tab', state.tab)
  if (state.from) {
    p.set('from', `${state.from.latitude.toFixed(6)},${state.from.longitude.toFixed(6)}`)
    p.set('fn', state.from.label)
    if (state.from.area) p.set('fa', state.from.area)
  }
  if (state.to) {
    p.set('to', `${state.to.latitude.toFixed(6)},${state.to.longitude.toFixed(6)}`)
    p.set('tn', state.to.label)
    if (state.to.area) p.set('ta', state.to.area)
  }
  if (state.time !== 'now') p.set('t', state.time)
  if (state.mode) p.set('mode', state.mode)
  const next = `${window.location.pathname}?${p}`
  if (next !== `${window.location.pathname}${window.location.search}`) window.history.replaceState(null, '', next)
}

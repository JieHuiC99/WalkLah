// Small walker-side helpers: Malaysia time choices, a random device ID, saved preferences and recent places.

import type { Place, RainMode } from '../types'
import { t, type Lang } from './i18n'

export type TimeChoice = 'now' | `${number}`

/** Hours offered in the "Leave at" picker (24 h clock, Malaysia time). */
export const TIME_CHOICES: TimeChoice[] = ['now', '8', '11', '13', '16', '18', '21']

const MY_TZ = 'Asia/Kuala_Lumpur'

function malaysiaParts(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: MY_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '00'
  return { date: `${get('year')}-${get('month')}-${get('day')}`, hour: Number(get('hour')), minute: Number(get('minute')) }
}

/** 'YYYY-MM-DDTHH:MM' Malaysia time for the API, or undefined for "now". */
export function atFor(choice: TimeChoice): string | undefined {
  if (choice === 'now') return undefined
  const { date } = malaysiaParts()
  return `${date}T${String(Number(choice)).padStart(2, '0')}:00`
}

/** Hour (0-23, Malaysia time) a choice refers to. */
export function hourFor(choice: TimeChoice): number {
  return choice === 'now' ? malaysiaParts().hour : Number(choice)
}

export function timeLabel(choice: TimeChoice): string {
  if (choice === 'now') return t('Now')
  const h = Number(choice)
  const suffix = h < 12 ? 'am' : 'pm'
  return `${h % 12 === 0 ? 12 : h % 12} ${suffix}`
}

export function greeting(): string {
  const { hour } = malaysiaParts()
  if (hour < 12) return t('Good morning!')
  if (hour < 18) return t('Good afternoon!')
  return t('Good evening!')
}

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Private mode or blocked storage: the preference just isn't remembered.
  }
}

let sessionDevice: string | null = null

/** Random per-phone ID for "one vote per device"; not linked to any person. */
export function deviceId(): string {
  const stored = safeGet('walklah.device')
  if (stored) return stored
  sessionDevice ??= `go-${crypto.randomUUID()}`
  safeSet('walklah.device', sessionDevice)
  return sessionDevice
}

export interface GoPrefs {
  walker: 'commute' | 'leisure' | null
  stepFree: boolean
  shareStats: boolean
  rain: RainMode
  lang: Lang
}

function defaultLang(): Lang {
  return typeof navigator !== 'undefined' && /^(ms|id)/i.test(navigator.language) ? 'ms' : 'en'
}

export function loadPrefs(): GoPrefs {
  const defaults: GoPrefs = { walker: null, stepFree: false, shareStats: false, rain: 'auto', lang: defaultLang() }
  try {
    const raw = safeGet('walklah.prefs')
    if (raw) return { ...defaults, ...JSON.parse(raw) }
  } catch {
    // ignore malformed storage
  }
  return defaults
}

export function savePrefs(prefs: GoPrefs): void {
  safeSet('walklah.prefs', JSON.stringify(prefs))
}

const RECENT_KEY = 'walklah.recent'
const RECENT_MAX = 6

/** Places the walker picked recently (on this phone only). */
export function loadRecent(): Place[] {
  try {
    const raw = safeGet(RECENT_KEY)
    const list = raw ? (JSON.parse(raw) as Place[]) : []
    return Array.isArray(list) ? list.slice(0, RECENT_MAX) : []
  } catch {
    return []
  }
}

export function rememberPlace(place: Place): void {
  const next = [place, ...loadRecent().filter((p) => p.id !== place.id)].slice(0, RECENT_MAX)
  safeSet(RECENT_KEY, JSON.stringify(next))
}

/** "350 m" / "2.4 km" */
export function distanceLabel(metres: number): string {
  return metres < 950 ? `${Math.round(metres / 10) * 10} m` : `${(metres / 1000).toFixed(1)} km`
}

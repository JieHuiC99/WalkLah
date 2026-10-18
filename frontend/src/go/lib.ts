// Small walker-side helpers: Malaysia time choices, a random device ID and saved preferences.

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
  if (choice === 'now') return 'Now'
  const h = Number(choice)
  const suffix = h < 12 ? 'am' : 'pm'
  return `${h % 12 === 0 ? 12 : h % 12} ${suffix}`
}

export function greeting(): string {
  const { hour } = malaysiaParts()
  if (hour < 12) return 'Good morning!'
  if (hour < 18) return 'Good afternoon!'
  return 'Good evening!'
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
}

export function loadPrefs(): GoPrefs {
  try {
    const raw = safeGet('walklah.prefs')
    if (raw) return { walker: null, stepFree: false, shareStats: false, ...JSON.parse(raw) }
  } catch {
    // ignore malformed storage
  }
  return { walker: null, stepFree: false, shareStats: false }
}

export function savePrefs(prefs: GoPrefs): void {
  safeSet('walklah.prefs', JSON.stringify(prefs))
}

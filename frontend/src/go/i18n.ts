// English / Bahasa Melayu for WalkLah Go. English text is the key; anything without a
// translation stays in English (never blank). Place and street names are never translated.

export type Lang = 'en' | 'ms'

let current: Lang = 'en'

export function setLanguage(lang: Lang): void {
  current = lang
  document.documentElement.lang = lang === 'ms' ? 'ms' : 'en'
}

export function language(): Lang {
  return current
}

/** Translate `text`, filling {placeholders} from vars. */
export function t(text: string, vars?: Record<string, string | number>): string {
  const template = current === 'ms' ? (MS[text] ?? text) : text
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (_, key: string) => (key in vars ? String(vars[key]) : `{${key}}`))
}

const MS: Record<string, string> = {}

/** Registers Bahasa Melayu strings (kept in i18n.ms.ts). */
export function registerMs(entries: Record<string, string>): void {
  Object.assign(MS, entries)
}

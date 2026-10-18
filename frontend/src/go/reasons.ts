// The API explains each route in fixed English sentences. These patterns turn them into
// translatable templates; a sentence that matches none is shown as sent.

import { language, t } from './i18n'

const PATTERNS: [RegExp, string, string[]][] = [
  [/^Avoids (\d+) verified barriers?$/, 'Avoids {n} verified barrier(s)', ['n']],
  [/^Avoids (\d+) hazards? confirmed by walkers$/, 'Avoids {n} hazard(s) confirmed by walkers', ['n']],
  [/^Rain likely \((\d+)%\): (\d+)% covered vs (\d+)% on the shortest route$/, 'Rain likely ({p}%): {a}% covered vs {b}% on the shortest route', ['p', 'a', 'b']],
  [/^Rain likely \((\d+)%\): (\d+)% covered$/, 'Rain likely ({p}%): {a}% covered', ['p', 'a']],
  [/^Rain cover on: (\d+)% covered vs (\d+)% on the shortest route$/, 'Rain cover on: {a}% covered vs {b}% on the shortest route', ['a', 'b']],
  [/^Rain cover on: (\d+)% covered$/, 'Rain cover on: {a}% covered', ['a']],
  [/^(\d+)% shaded at this time$/, '{a}% shaded at this time', ['a']],
  [/^(\d+)% shaded vs (\d+)% on the shortest route$/, '{a}% shaded vs {b}% on the shortest route', ['a', 'b']],
  [/^(\d+)% on paths known to be lit · (\d+)% lighting unknown$/, '{a}% on paths known to be lit · {b}% lighting unknown', ['a', 'b']],
  [/^(\d+) m less along busy roads$/, '{n} m less along busy roads', ['n']],
  [/^No steps$/, 'No steps', []],
  [/^(\d+) flights? of steps$/, '{n} flight(s) of steps', ['n']],
  [/^(\d+) m on roads with unknown sidewalk$/, '{n} m on roads with unknown sidewalk', ['n']],
  [/^(\d+) unverified reports? on this route$/, '{n} unverified report(s) on this route', ['n']],
]

export function reasonText(reason: string): string {
  if (language() === 'en') return reason
  if (reason.startsWith('Crossings: ')) {
    const parts = reason
      .slice('Crossings: '.length)
      .split(', ')
      .map((part) => {
        const [n, kind] = part.split(' ')
        return `${n} ${t(kind)}`
      })
    return `${t('Crossings')}: ${parts.join(', ')}`
  }
  for (const [pattern, template, names] of PATTERNS) {
    const match = reason.match(pattern)
    if (match) {
      const vars = Object.fromEntries(names.map((name, i) => [name, match[i + 1]]))
      return t(template, vars)
    }
  }
  return reason
}

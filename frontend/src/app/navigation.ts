// Tab + route selection live in the query string so a rehearsed demo link opens preloaded,
// e.g. ?tab=explore&from=start_1&to=destination_2 ("navigate" is accepted as an alias).

export type Tab = 'home' | 'explore' | 'report' | 'community' | 'operator'

export const TABS: Tab[] = ['home', 'explore', 'report', 'community', 'operator']

/** Which S.T.E.P. stage each screen belongs to (Survey lives in the Map data sheet). */
export const TAB_STAGE: Record<Tab, StepStage | null> = {
  home: null,
  explore: 'E',
  report: 'T',
  community: 'T',
  operator: 'P',
}

export type StepStage = 'S' | 'T' | 'E' | 'P'

const ALIASES: Record<string, Tab> = { navigate: 'explore', dashboard: 'operator' }

export interface UrlState {
  tab: Tab
  from: string | null
  to: string | null
}

export function readUrlState(): UrlState {
  const params = new URLSearchParams(window.location.search)
  const rawTab = params.get('tab') ?? 'home'
  const tab = (ALIASES[rawTab] ?? (TABS.includes(rawTab as Tab) ? rawTab : 'home')) as Tab
  return { tab, from: params.get('from'), to: params.get('to') }
}

export function writeUrlState({ tab, from, to }: UrlState): void {
  const params = new URLSearchParams()
  params.set('tab', tab)
  if (from) params.set('from', from)
  if (to) params.set('to', to)
  const next = `${window.location.pathname}?${params}`
  if (next !== `${window.location.pathname}${window.location.search}`) {
    window.history.replaceState(null, '', next)
  }
}

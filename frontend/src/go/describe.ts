// Walker-facing sentences built from structured API fields, so they work in English and Bahasa Melayu.

import { categoryLabel } from '../config/categories'
import type { RouteAlert, RouteStep } from '../types'
import { t } from './i18n'
import { distanceLabel } from './lib'

export function stepText(step: RouteStep): string {
  const way = step.name ?? t(step.way ?? 'the path')
  switch (step.type) {
    case 'depart':
      return t('Head {dir} on {way}', { dir: t(step.direction ?? 'ahead'), way })
    case 'turn':
      if (step.modifier?.startsWith('slight')) {
        return t('Keep {side} onto {way}', { side: t(step.modifier.split(' ')[1]), way })
      }
      return t('Turn {mod} onto {way}', { mod: t(step.modifier ?? 'ahead'), way })
    case 'continue':
      return t('Continue onto {way}', { way })
    case 'steps':
      return step.modifier ? t('Take the steps, then {mod}', { mod: t(step.modifier) }) : t('Take the steps')
    case 'arrive':
      return t('Arrive at your destination')
    default:
      return step.instruction
  }
}

export function alertText(alert: RouteAlert): string {
  const d = alert.length_m !== null ? distanceLabel(alert.length_m) : ''
  switch (alert.type) {
    case 'sun':
      return t('Sunny stretch: {d} without shade', { d })
    case 'unlit':
      return t('Unlit stretch: {d}', { d })
    case 'light_unknown':
      return t('Lighting unknown for {d}', { d })
    case 'uncovered':
      return t('No cover for {d}', { d })
    case 'steps':
      return t('Steps ahead')
    case 'crossing':
      return t(alert.text)
    case 'hazard':
      return t('Reported: {what} (not verified)', { what: t(categoryLabel(alert.category ?? 'other')) })
    default:
      return alert.text
  }
}

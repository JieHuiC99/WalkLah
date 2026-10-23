import type { LatLon } from '../types'

export type GoTab = 'home' | 'explore' | 'report' | 'community'

/** A chosen start or destination: a named place, a dropped pin or the phone's location. */
export interface Endpoint extends LatLon {
  label: string
  /** Neighbourhood/town of a place, to tell branches apart. */
  area?: string | null
  source: 'place' | 'pin' | 'gps'
}

export type PickTarget = 'from' | 'to' | 'report'

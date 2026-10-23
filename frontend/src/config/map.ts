import type { LngLatBoundsLike } from 'maplibre-gl'

/** Malaysia (Peninsular, Sabah, Sarawak; Singapore and Brunei fall inside too). */
export const DATA_BOUNDS = { south: 0.8, north: 7.5, west: 99.5, east: 119.5 } as const

/** Default view before the walker's location is known: central Kuala Lumpur and the Klang Valley. */
export const MAP_CENTER: [number, number] = [101.6869, 3.139] // [lon, lat]
export const MAP_ZOOM = 12.5
/** Zoom used when centring on a person or a place. */
export const STREET_ZOOM = 16

const PAD = 1
/** The camera may not wander far outside Malaysia. */
export const MAX_BOUNDS: LngLatBoundsLike = [
  [DATA_BOUNDS.west - PAD, DATA_BOUNDS.south - PAD],
  [DATA_BOUNDS.east + PAD, DATA_BOUNDS.north + PAD],
]

export const MAP_STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/positron'

/** Points can only be chosen inside the area WalkLah covers. */
export function isInsideDataBounds(lat: number, lon: number): boolean {
  return lat >= DATA_BOUNDS.south && lat <= DATA_BOUNDS.north && lon >= DATA_BOUNDS.west && lon <= DATA_BOUNDS.east
}

export const COLORS = {
  forest: '#10231c',
  green: '#14915f',
  greenBright: '#1fb574',
  kuning: '#f6c445',
  kuningDeep: '#c99a14',
  red: '#e5484d',
  amber: '#f0a500',
  sun: '#f28c28',
  unknown: '#b9b2a0',
  grey: '#8e887a',
  baselineDots: '#5b6b63',
  blue: '#1d5fa8',
  cream: '#fbf8f1',
} as const

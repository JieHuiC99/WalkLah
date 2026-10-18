import type { LngLatBoundsLike } from 'maplibre-gl'

/** Area covered by the backend's pedestrian graph (2 km around 3.118, 101.655). */
export const DATA_BOUNDS = { south: 3.1, north: 3.136, west: 101.637, east: 101.673 } as const

export const MAP_CENTER: [number, number] = [101.6585, 3.1175] // [lon, lat], between LRT Universiti and campus
export const MAP_ZOOM = 15.3

const PAD = 0.01
/** The camera may not wander far outside the data area. */
export const MAX_BOUNDS: LngLatBoundsLike = [
  [DATA_BOUNDS.west - PAD, DATA_BOUNDS.south - PAD],
  [DATA_BOUNDS.east + PAD, DATA_BOUNDS.north + PAD],
]

export const MAP_STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/positron'

/** Points can only be chosen inside the data area. */
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

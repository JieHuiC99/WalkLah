import type { Map as MapLibreMap, StyleSpecification } from 'maplibre-gl'

// Recolours the OpenFreeMap "positron" layers into the WalkLah palette (cream land, mint
// parks, soft blue water, visible footpaths). Layers missing from another style are skipped.
const PAINT: Record<string, Record<string, unknown>> = {
  background: { 'background-color': '#f2eee3' },
  park: { 'fill-color': '#cdebd7', 'fill-opacity': 1 },
  landcover_wood: { 'fill-color': '#d5ecd9', 'fill-opacity': 0.9 },
  landuse_residential: { 'fill-color': '#ece6d6', 'fill-opacity': 0.6 },
  water: { 'fill-color': '#bfe3f2' },
  building: { 'fill-color': '#e6e0d0', 'fill-outline-color': '#dcd4c1' },
  highway_path: { 'line-color': '#b8ad92', 'line-dasharray': [2, 1.5] },
  highway_minor: { 'line-color': '#ffffff' },
  highway_major_casing: { 'line-color': '#e3dccb' },
  highway_major_inner: { 'line-color': '#fdf3d3' },
  highway_motorway_inner: { 'line-color': '#fce7a6' },
  highway_motorway_casing: { 'line-color': '#efcf6b' },
}

export function applyWalkLahPalette(map: MapLibreMap): void {
  for (const [layerId, paint] of Object.entries(PAINT)) {
    if (!map.getLayer(layerId)) continue
    for (const [property, value] of Object.entries(paint)) {
      try {
        map.setPaintProperty(layerId, property as never, value as never)
      } catch {
        // A property the layer type doesn't support; keep the style's own value.
      }
    }
  }
}

/** Used when the base map can't load (e.g. venue wifi down): routes and reports still draw on it. */
export const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#f2eee3' } }],
}

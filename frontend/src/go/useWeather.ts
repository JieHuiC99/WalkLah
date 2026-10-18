import { useEffect, useState } from 'react'
import type { LatLon } from '../types'

// Hourly forecast where the walker is looking, from Open-Meteo (free, no key; CC BY 4.0, credited in the app).
// Shown as context; rain cover in routing uses the backend's own forecast lookup.
function urlFor(lat: number, lon: number): string {
  return (
    `https://api.open-meteo.com/v1/forecast?latitude=${lat.toFixed(1)}&longitude=${lon.toFixed(1)}` +
    '&hourly=temperature_2m,uv_index,precipitation_probability,cloud_cover&timezone=Asia%2FKuala_Lumpur&forecast_days=1'
  )
}

export interface HourWeather {
  temperature: number
  uv: number
  rain: number
  cloud: number
}

export function useWeather(near: LatLon | null): { byHour: HourWeather[] | null; failed: boolean } {
  const [byHour, setByHour] = useState<HourWeather[] | null>(null)
  const [failed, setFailed] = useState(false)
  // ~10 km cells: panning around a town doesn't refetch.
  const lat = near ? Math.round(near.latitude * 10) / 10 : null
  const lon = near ? Math.round(near.longitude * 10) / 10 : null
  useEffect(() => {
    if (lat === null || lon === null) return
    const controller = new AbortController()
    fetch(urlFor(lat, lon), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data) => {
        const h = data.hourly
        setByHour(
          (h.time as string[]).map((_, i) => ({
            temperature: h.temperature_2m[i],
            uv: h.uv_index[i],
            rain: h.precipitation_probability[i],
            cloud: h.cloud_cover[i],
          })),
        )
        setFailed(false)
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => controller.abort()
  }, [lat, lon])
  return { byHour, failed }
}

export function uvLabel(uv: number): string {
  if (uv >= 11) return 'extreme'
  if (uv >= 8) return 'very high'
  if (uv >= 6) return 'high'
  if (uv >= 3) return 'moderate'
  return 'low'
}

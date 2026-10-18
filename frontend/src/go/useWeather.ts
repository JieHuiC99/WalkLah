import { useEffect, useState } from 'react'

// Hourly forecast for UM from Open-Meteo (free, no key; CC BY 4.0, credited in the app).
// Context only: it is never used in the route cost.
const URL =
  'https://api.open-meteo.com/v1/forecast?latitude=3.118&longitude=101.655' +
  '&hourly=temperature_2m,uv_index,precipitation_probability,cloud_cover&timezone=Asia%2FKuala_Lumpur&forecast_days=1'

export interface HourWeather {
  temperature: number
  uv: number
  rain: number
  cloud: number
}

export function useWeather(): { byHour: HourWeather[] | null; failed: boolean } {
  const [byHour, setByHour] = useState<HourWeather[] | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch(URL, { signal: controller.signal })
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
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => controller.abort()
  }, [])
  return { byHour, failed }
}

export function uvLabel(uv: number): string {
  if (uv >= 11) return 'extreme'
  if (uv >= 8) return 'very high'
  if (uv >= 6) return 'high'
  if (uv >= 3) return 'moderate'
  return 'low'
}

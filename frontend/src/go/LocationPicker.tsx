import { useEffect, useState } from 'react'
import * as api from '../api/walklahApi'
import { Icon, type IconName } from '../components/icons'
import { isInsideDataBounds } from '../config/map'
import type { Place } from '../types'
import { Sheet } from './Sheet'
import type { Endpoint } from './types'

const PLACE_ICONS: Record<string, IconName> = {
  transit: 'train',
  campus: 'book',
  daily: 'coffee',
  leisure: 'leaf',
  health: 'heart',
  other: 'pin',
}

function placeIcon(place: Place): IconName {
  if (place.kind === 'bus_stop') return 'bus'
  return PLACE_ICONS[place.category] ?? 'pin'
}

function placeHint(place: Place): string {
  if (place.kind === 'rail_station') return 'LRT station'
  if (place.kind === 'bus_stop') return 'Bus stop'
  return { campus: 'Campus', daily: 'Food & daily needs', leisure: 'Leisure', health: 'Health', transit: 'Transit', other: 'Place' }[
    place.category
  ]
}

interface Props {
  which: 'from' | 'to'
  featured: Place[]
  onChoose: (endpoint: Endpoint) => void
  onPickOnMap: () => void
  onClose: () => void
}

export function LocationPicker({ which, featured, onChoose, onPickOnMap, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Place[] | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [locating, setLocating] = useState(false)
  const [gpsError, setGpsError] = useState<string | null>(null)

  // Debounced search; an empty query shows the featured quick picks.
  useEffect(() => {
    const q = query.trim()
    if (!q) return
    const timer = window.setTimeout(() => {
      api.searchPlaces(q).then(
        (places) => {
          setResults(places)
          setSearchError(null)
        },
        (error: unknown) => setSearchError(api.errorMessage(error)),
      )
    }, 250)
    return () => window.clearTimeout(timer)
  }, [query])

  const useMyLocation = () => {
    if (!('geolocation' in navigator)) {
      setGpsError('This browser has no location access.')
      return
    }
    setLocating(true)
    setGpsError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        const { latitude, longitude } = pos.coords
        if (!isInsideDataBounds(latitude, longitude)) {
          setGpsError("You're outside the WalkLah pilot map (around Universiti Malaya). Pick a place or drop a pin instead.")
          return
        }
        onChoose({ latitude, longitude, label: 'Your location', source: 'gps' })
      },
      (error) => {
        setLocating(false)
        setGpsError(error.code === error.PERMISSION_DENIED ? 'Location permission was denied.' : "Couldn't get your location.")
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  const list = query.trim() ? (results ?? []) : featured

  return (
    <Sheet title={which === 'from' ? 'Choose start' : 'Choose destination'} onClose={onClose} tall>
      <label className="search-field">
        <Icon name="search" size={18} />
        <input
          type="search"
          value={query}
          placeholder="Search a place, building or stop"
          autoComplete="off"
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>

      <div className="picker-actions">
        <button type="button" className="picker-action" onClick={useMyLocation} disabled={locating}>
          <Icon name="locate" size={18} /> {locating ? 'Finding you…' : 'Your location'}
        </button>
        <button type="button" className="picker-action" onClick={onPickOnMap}>
          <Icon name="pin" size={18} /> Choose on map
        </button>
      </div>
      {gpsError && <p className="inline-error">{gpsError}</p>}
      {searchError && <p className="inline-error">{searchError}</p>}

      <h3 className="picker-heading">{query.trim() ? 'Results' : 'Suggested'}</h3>
      {query.trim() && results && results.length === 0 && <p className="empty-note">No places match "{query}".</p>}
      <ul className="place-list">
        {list.map((place) => (
          <li key={place.id}>
            <button
              type="button"
              className="place-row"
              onClick={() =>
                onChoose({ latitude: place.latitude, longitude: place.longitude, label: place.name, source: 'place' })
              }
            >
              <span className={`place-row__icon place-row__icon--${place.kind ?? place.category}`}>
                <Icon name={placeIcon(place)} size={18} />
              </span>
              <span className="place-row__text">
                <strong>{place.name}</strong>
                <span>{placeHint(place)}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      <p className="fine-print">Places from OpenStreetMap. Any point on the map works too.</p>
    </Sheet>
  )
}

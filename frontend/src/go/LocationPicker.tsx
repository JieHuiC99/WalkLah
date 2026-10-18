import { useEffect, useState } from 'react'
import * as api from '../api/walklahApi'
import { Icon, type IconName } from '../components/icons'
import { isInsideDataBounds } from '../config/map'
import type { LatLon, Place } from '../types'
import { t } from './i18n'
import { distanceLabel, loadRecent, rememberPlace } from './lib'
import { Sheet } from './Sheet'
import type { Endpoint } from './types'

const PLACE_ICONS: Record<string, IconName> = {
  transit: 'train',
  food: 'food',
  shopping: 'bag',
  campus: 'book',
  daily: 'coffee',
  leisure: 'leaf',
  health: 'heart',
  civic: 'flag',
  other: 'pin',
}

function placeIcon(place: Place): IconName {
  if (place.kind === 'bus_stop') return 'bus'
  return PLACE_ICONS[place.category] ?? 'pin'
}

function placeHint(place: Place): string {
  if (place.kind === 'rail_station') return t('Station')
  if (place.kind === 'station_entrance') return t('Station entrance')
  if (place.kind === 'bus_stop') return t('Bus stop')
  const labels: Record<string, string> = {
    food: 'Food & drink',
    shopping: 'Shop',
    campus: 'Education',
    daily: 'Food & daily needs',
    leisure: 'Leisure',
    health: 'Health',
    civic: 'Public service',
    transit: 'Transit',
    other: 'Place',
  }
  return t(labels[place.category] ?? 'Place')
}

type Chip = { id: string; label: string; icon: IconName; filter: { kind?: string; category?: string } }

const CHIPS: Chip[] = [
  { id: 'rail', label: 'Nearest LRT/MRT', icon: 'train', filter: { kind: 'rail_station' } },
  { id: 'food', label: 'Food', icon: 'food', filter: { category: 'food' } },
  { id: 'shopping', label: 'Shopping', icon: 'bag', filter: { category: 'shopping' } },
  { id: 'bus', label: 'Bus stops', icon: 'bus', filter: { kind: 'bus_stop' } },
]

interface Props {
  which: 'from' | 'to'
  /** Where the walker is looking (map centre) or standing; results are ranked around it. */
  near: LatLon | null
  featured: Place[]
  onChoose: (endpoint: Endpoint) => void
  onPickOnMap: () => void
  onClose: () => void
}

export function LocationPicker({ which, near, featured, onChoose, onPickOnMap, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Place[] | null>(null)
  const [chip, setChip] = useState<Chip | null>(null)
  const [chipResults, setChipResults] = useState<Place[] | null>(null)
  const [nearby, setNearby] = useState<Place[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)
  const [locating, setLocating] = useState(false)
  const [gpsError, setGpsError] = useState<string | null>(null)
  const [recent] = useState<Place[]>(loadRecent)

  // Debounced search, ranked around the map centre.
  useEffect(() => {
    const q = query.trim()
    if (!q) return
    const timer = window.setTimeout(() => {
      api.searchPlaces(q, near).then(
        (places) => {
          setResults(places)
          setSearchError(null)
        },
        (error: unknown) => setSearchError(api.errorMessage(error)),
      )
    }, 220)
    return () => window.clearTimeout(timer)
  }, [query, near])

  // Stations around the map centre as the default suggestions.
  useEffect(() => {
    if (!near) return
    let cancelled = false
    api.searchPlaces('', near).then(
      (places) => !cancelled && setNearby(places),
      () => undefined,
    )
    return () => {
      cancelled = true
    }
  }, [near])

  useEffect(() => {
    if (!chip || !near) return
    let cancelled = false
    api.nearbyPlaces(near, chip.filter, chip.filter.kind === 'rail_station' ? 6000 : 2000).then(
      (places) => {
        if (cancelled) return
        setChipResults(places)
        setSearchError(null)
      },
      (error: unknown) => !cancelled && setSearchError(api.errorMessage(error)),
    )
    return () => {
      cancelled = true
    }
  }, [chip, near])

  const choosePlace = (place: Place) => {
    rememberPlace({ ...place, distance_m: undefined })
    onChoose({
      latitude: place.latitude,
      longitude: place.longitude,
      label: place.name,
      area: place.area ?? null,
      source: 'place',
    })
  }

  const useMyLocation = () => {
    if (!('geolocation' in navigator)) {
      setGpsError(t('This browser has no location access.'))
      return
    }
    setLocating(true)
    setGpsError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false)
        const { latitude, longitude } = pos.coords
        if (!isInsideDataBounds(latitude, longitude)) {
          setGpsError(t("You're outside Malaysia. Search for a place or drop a pin instead."))
          return
        }
        onChoose({ latitude, longitude, label: t('Your location'), source: 'gps' })
      },
      (error) => {
        setLocating(false)
        setGpsError(
          error.code === error.PERMISSION_DENIED ? t('Location permission was denied.') : t("Couldn't get your location."),
        )
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  const searching = query.trim().length > 0
  let heading: string
  let list: Place[]
  if (searching) {
    heading = t('Results')
    list = results ?? []
  } else if (chip) {
    heading = t(chip.label)
    list = chipResults ?? []
  } else {
    heading = ''
    list = []
  }

  return (
    <Sheet title={which === 'from' ? t('Choose start') : t('Choose destination')} onClose={onClose} tall>
      <label className="search-field">
        <Icon name="search" size={18} />
        <input
          type="search"
          value={query}
          placeholder={t('Search stations, shops, branches…')}
          autoComplete="off"
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>

      <div className="picker-actions">
        <button type="button" className="picker-action" onClick={useMyLocation} disabled={locating}>
          <Icon name="locate" size={18} /> {locating ? t('Finding you…') : t('Your location')}
        </button>
        <button type="button" className="picker-action" onClick={onPickOnMap}>
          <Icon name="pin" size={18} /> {t('Choose on map')}
        </button>
      </div>
      {gpsError && <p className="inline-error">{gpsError}</p>}
      {searchError && <p className="inline-error">{searchError}</p>}

      {!searching && near && (
        <div className="chip-row picker-chips" role="group" aria-label={t('Nearby')}>
          {CHIPS.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`chip${chip?.id === c.id ? ' is-active' : ''}`}
              aria-pressed={chip?.id === c.id}
              onClick={() => {
                setChipResults(null)
                setChip(chip?.id === c.id ? null : c)
              }}
            >
              <Icon name={c.icon} size={14} /> {t(c.label)}
            </button>
          ))}
        </div>
      )}

      {(searching || chip) && (
        <>
          <h3 className="picker-heading">{heading}</h3>
          {searching && results && results.length === 0 && (
            <p className="empty-note">{t('No places match "{q}".', { q: query })}</p>
          )}
          {chip && chipResults && chipResults.length === 0 && <p className="empty-note">{t('Nothing found nearby.')}</p>}
          <PlaceList places={list} onChoose={choosePlace} />
        </>
      )}

      {!searching && !chip && (
        <>
          {recent.length > 0 && (
            <>
              <h3 className="picker-heading">{t('Recent')}</h3>
              <PlaceList places={recent} onChoose={choosePlace} icon="clock" />
            </>
          )}
          {(nearby.length > 0 || featured.length > 0) && (
            <>
              <h3 className="picker-heading">{nearby.length > 0 ? t('Stations nearby') : t('Suggested')}</h3>
              <PlaceList places={nearby.length > 0 ? nearby : featured} onChoose={choosePlace} />
            </>
          )}
        </>
      )}
      <p className="fine-print">{t('Places from OpenStreetMap and Overture Maps. Any point on the map works too.')}</p>
    </Sheet>
  )
}

function PlaceList({ places, onChoose, icon }: { places: Place[]; onChoose: (p: Place) => void; icon?: IconName }) {
  return (
    <ul className="place-list">
      {places.map((place) => (
        <li key={place.id}>
          <button type="button" className="place-row" onClick={() => onChoose(place)}>
            <span className={`place-row__icon place-row__icon--${place.kind ?? place.category}`}>
              <Icon name={icon ?? placeIcon(place)} size={18} />
            </span>
            <span className="place-row__text">
              <strong>{place.name}</strong>
              <span>
                {[placeHint(place), place.area, place.distance_m !== undefined ? distanceLabel(place.distance_m) : null]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

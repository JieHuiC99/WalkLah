import { useEffect, useState, type FormEvent } from 'react'
import * as api from '../../api/walklahApi'
import { CategoryIcon } from '../../components/CategoryIcon'
import { Icon } from '../../components/icons'
import { StatusBadge } from '../../components/StatusBadge'
import { CATEGORIES, durationLabel } from '../../config/categories'
import { DEMO_MODE, DEMO_OBSTACLE } from '../../config/demo'
import { isInsideDataBounds } from '../../config/map'
import type { LatLon, NearSegment, Report } from '../../types'

const MAX_DESCRIPTION = 280
const HIGHWAY_LABELS: Record<string, string> = {
  footway: 'Footpath',
  path: 'Path',
  pedestrian: 'Pedestrian street',
  steps: 'Steps',
  corridor: 'Covered corridor',
  service: 'Service road',
  residential: 'Residential road',
  tertiary: 'Road',
  secondary: 'Main road',
  primary: 'Main road',
}

interface Props {
  point: LatLon | null
  onPoint: (point: LatLon | null) => void
  onSubmitted: () => Promise<void>
  onCommunity: () => void
}

export function ReportScreen({ point, onPoint, onSubmitted, onCommunity }: Props) {
  const [category, setCategory] = useState<string | null>(null)
  const [description, setDescription] = useState('')
  const [candidates, setCandidates] = useState<NearSegment[]>([])
  const [segment, setSegment] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState<Report | null>(null)

  const outside = point ? !isInsideDataBounds(point.latitude, point.longitude) : false

  // When the pin could belong to more than one path (parallel roads, bridges, crossings),
  // the walker confirms which one; otherwise the server snaps it.
  useEffect(() => {
    if (!point || outside) return
    let cancelled = false
    api.nearSegments(point.latitude, point.longitude).then(
      (found) => {
        if (cancelled) return
        const ambiguous = found.length > 1 && found[1].distance_m - found[0].distance_m < 10
        setCandidates(ambiguous ? found : [])
        setSegment(ambiguous ? found[0].segment_id : null)
      },
      () => !cancelled && setCandidates([]),
    )
    return () => {
      cancelled = true
    }
  }, [point, outside])

  const useMyLocation = () => {
    navigator.geolocation?.getCurrentPosition(
      (pos) => onPoint({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
      () => setError("Couldn't get your location. Tap the map instead."),
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!point) return setError('Tap the map where the problem is.')
    if (outside) return setError('That spot is outside the WalkLah map.')
    if (!category) return setError('Choose what the issue is.')
    setSubmitting(true)
    try {
      const report = await api.createReport({
        category,
        description: description.trim() || null,
        latitude: point.latitude,
        longitude: point.longitude,
        ...(segment && candidates.length > 0 ? { segment_id: segment } : {}),
      })
      await onSubmitted()
      setSubmitted(report)
      setCategory(null)
      setDescription('')
      setCandidates([])
    } catch (err) {
      // Keep everything the walker entered so they can retry.
      setError(api.errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <div className="go-screen">
        <h1 className="go-title">Report sent</h1>
        <div className="success-card" role="status">
          <Icon name="check" size={22} />
          <div>
            <strong>Thanks — it's pending verification.</strong>
            <p>
              Other walkers can confirm it, and an operator verifies it before routes avoid it.
              {submitted.temporary_or_permanent === 'temporary' && ' Temporary issues expire unless someone reconfirms them.'}
            </p>
            <StatusBadge status={submitted.status} />
          </div>
        </div>
        <div className="button-row">
          <button type="button" className="btn" onClick={onCommunity}>
            Community updates
          </button>
          <button type="button" className="btn btn--primary" onClick={() => setSubmitted(null)}>
            Report another
          </button>
        </div>
      </div>
    )
  }

  return (
    <form className="go-screen" onSubmit={submit} noValidate>
      <h1 className="go-title">Report an issue</h1>

      <div className={`location-card${point ? ' has-point' : ''}${outside ? ' is-invalid' : ''}`}>
        <Icon name="pin" size={20} className="location-card__icon" />
        <div className="location-card__text">
          {point ? (
            <>
              <strong>{outside ? 'Outside the WalkLah map' : 'Spot marked'}</strong>
              <span>Drag the pin to adjust</span>
            </>
          ) : (
            <>
              <strong>Tap the map where it is</strong>
              <span>It's linked to the nearest path</span>
            </>
          )}
        </div>
        {point ? (
          <button type="button" className="icon-btn" onClick={() => onPoint(null)} aria-label="Clear location">
            <Icon name="x" size={18} />
          </button>
        ) : (
          <button type="button" className="btn btn--small" onClick={useMyLocation}>
            Here
          </button>
        )}
      </div>
      {DEMO_MODE && !point && (
        <button type="button" className="btn btn--ghost demo-link" onClick={() => onPoint({ ...DEMO_OBSTACLE })}>
          <Icon name="target" size={16} /> Use rehearsed demo spot
        </button>
      )}

      {point && !outside && candidates.length > 0 && (
        <fieldset className="go-field">
          <legend className="go-label">Which path is it on?</legend>
          <div className="candidate-list">
            {candidates.map((c) => (
              <label key={c.segment_id} className={`candidate${segment === c.segment_id ? ' is-selected' : ''}`}>
                <input
                  type="radio"
                  name="segment"
                  checked={segment === c.segment_id}
                  onChange={() => setSegment(c.segment_id)}
                />
                <span>
                  <strong>{c.name ?? HIGHWAY_LABELS[c.highway] ?? 'Path'}</strong>
                  <span>
                    {HIGHWAY_LABELS[c.highway] ?? c.highway} · {Math.round(c.distance_m)} m away
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <fieldset className="go-field">
        <legend className="go-label">What's the issue?</legend>
        <div className="category-tiles" role="radiogroup" aria-label="Category">
          {CATEGORIES.map((c) => (
            <button
              key={c.value}
              type="button"
              role="radio"
              aria-checked={category === c.value}
              className={`category-tile${category === c.value ? ' is-selected' : ''}`}
              onClick={() => setCategory(c.value)}
            >
              <CategoryIcon category={c.value} size={20} />
              <span>
                {c.label}
                {durationLabel(c.value) && <small>{durationLabel(c.value)}</small>}
              </span>
            </button>
          ))}
        </div>
      </fieldset>

      <label className="go-field">
        <span className="go-label">
          Description <span className="muted">(optional)</span>
        </span>
        <textarea
          value={description}
          maxLength={MAX_DESCRIPTION}
          rows={2}
          placeholder="What did you see?"
          onChange={(e) => setDescription(e.target.value)}
        />
        <span className="char-count">
          {description.length}/{MAX_DESCRIPTION}
        </span>
      </label>

      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}

      <button type="submit" className="btn btn--primary btn--block btn--large" disabled={submitting}>
        {submitting ? (
          <>
            <span className="spinner" aria-hidden="true" /> Sending…
          </>
        ) : (
          <>
            <Icon name="shoe" size={20} className="accent-icon" /> Submit report
          </>
        )}
      </button>
      <p className="fine-print center">Photos are on the roadmap; for now, describe what you saw.</p>
    </form>
  )
}

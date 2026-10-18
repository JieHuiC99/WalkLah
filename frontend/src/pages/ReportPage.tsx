import { useState, type FormEvent } from 'react'
import * as api from '../api/walklahApi'
import type { StepStage } from '../app/navigation'
import { CategoryIcon } from '../components/CategoryIcon'
import { Icon } from '../components/icons'
import type { LatLon } from '../components/MapView'
import { ScreenHeader } from '../components/ScreenHeader'
import { StatusBadge } from '../components/StatusBadge'
import { CATEGORIES, type CategoryDuration } from '../config/categories'
import { DEMO_MODE, DEMO_OBSTACLE } from '../config/demo'
import { isInsideDataBounds } from '../config/map'
import type { Report } from '../types'

const MAX_DESCRIPTION = 280

interface Props {
  draft: LatLon | null
  onUseDemoSpot: () => void
  onClearDraft: () => void
  onSubmitted: (report: Report) => Promise<void>
  onOpenCommunity: () => void
  onStage: (stage: StepStage) => void
}

export function ReportPage({ draft, onUseDemoSpot, onClearDraft, onSubmitted, onOpenCommunity, onStage }: Props) {
  const [duration, setDuration] = useState<Exclude<CategoryDuration, 'either'>>('temporary')
  const [category, setCategory] = useState<string | null>(null)
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState<Report | null>(null)

  const tiles = CATEGORIES.filter((c) => c.duration === duration || c.duration === 'either')
  const outside = draft ? !isInsideDataBounds(draft.latitude, draft.longitude) : false

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!draft) return setError('Tap the map to mark where the problem is.')
    if (outside) return setError('That spot is outside the WalkLah demo area around Universiti Malaya.')
    if (!category) return setError('Choose what the issue is.')
    setSubmitting(true)
    try {
      const report = await api.createReport({
        category,
        description: description.trim() || null,
        latitude: draft.latitude,
        longitude: draft.longitude,
      })
      await onSubmitted(report)
      setSubmitted(report)
      setCategory(null)
      setDescription('')
    } catch (err) {
      // Keep everything the user entered so they can retry.
      setError(api.errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <div className="report">
        <ScreenHeader title="Report sent" stage="T" onStage={onStage} />
        <div className="success-card" role="status">
          <Icon name="check" size={22} />
          <div>
            <strong>Reported — pending verification.</strong>
            <p>Pending reports don't change routes. An operator verifies it before WalkLah avoids it.</p>
            <StatusBadge status={submitted.status} />
          </div>
        </div>
        <div className="button-row">
          <button type="button" className="btn" onClick={onOpenCommunity}>
            See community updates
          </button>
          <button type="button" className="btn btn--primary" onClick={() => setSubmitted(null)}>
            Report another
          </button>
        </div>
      </div>
    )
  }

  return (
    <form className="report" onSubmit={submit} noValidate>
      <ScreenHeader title="Report an issue" subtitle="Help the next walker avoid it." stage="T" onStage={onStage} />

      <div className={`location-card${draft ? ' has-point' : ''}${outside ? ' is-invalid' : ''}`}>
        <Icon name="pin" size={20} className="location-card__icon" />
        <div className="location-card__text">
          {draft ? (
            <>
              <strong>{outside ? 'Outside the demo area' : 'Location set'}</strong>
              <span>
                {draft.latitude.toFixed(5)}, {draft.longitude.toFixed(5)} · drag the pin to adjust
              </span>
            </>
          ) : (
            <>
              <strong>Tap the map to mark the spot</strong>
              <span>The server links it to the nearest footpath.</span>
            </>
          )}
        </div>
        {draft && (
          <button type="button" className="icon-btn" onClick={onClearDraft} aria-label="Clear location">
            <Icon name="x" size={18} />
          </button>
        )}
      </div>
      {DEMO_MODE && (
        <button type="button" className="btn btn--ghost demo-link" onClick={onUseDemoSpot}>
          <Icon name="target" size={16} /> Use rehearsed demo spot ({DEMO_OBSTACLE.latitude}, {DEMO_OBSTACLE.longitude})
        </button>
      )}

      <fieldset className="report__field">
        <legend>What's the issue?</legend>
        <div className="segmented" role="radiogroup" aria-label="How long will it last?">
          {(['temporary', 'permanent'] as const).map((d) => (
            <button
              key={d}
              type="button"
              role="radio"
              aria-checked={duration === d}
              className={duration === d ? 'is-active' : ''}
              onClick={() => {
                setDuration(d)
                if (category && !CATEGORIES.some((c) => c.value === category && (c.duration === d || c.duration === 'either'))) {
                  setCategory(null)
                }
              }}
            >
              {d === 'temporary' ? 'Temporary' : 'Permanent'}
            </button>
          ))}
        </div>
        <div className="category-tiles" role="radiogroup" aria-label="Category">
          {tiles.map((c) => (
            <button
              key={c.value}
              type="button"
              role="radio"
              aria-checked={category === c.value}
              className={`category-tile${category === c.value ? ' is-selected' : ''}`}
              onClick={() => setCategory(c.value)}
            >
              <CategoryIcon category={c.value} size={20} />
              {c.label}
            </button>
          ))}
        </div>
      </fieldset>

      <label className="report__field">
        <span className="report__label">
          Description <span className="muted">(optional)</span>
        </span>
        <textarea
          value={description}
          maxLength={MAX_DESCRIPTION}
          rows={3}
          placeholder="What did you see? e.g. hoarding across the walkway"
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
      <p className="fine-print center">Reports start as pending until an operator verifies them.</p>
    </form>
  )
}

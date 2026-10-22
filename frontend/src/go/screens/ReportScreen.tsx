import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import * as api from '../../api/walklahApi'
import { CategoryIcon } from '../../components/CategoryIcon'
import { Icon } from '../../components/icons'
import { StatusBadge } from '../../components/StatusBadge'
import { CATEGORIES, durationLabel } from '../../config/categories'
import { isInsideDataBounds } from '../../config/map'
import type { LatLon, NearSegment, Report } from '../../types'
import { t } from '../i18n'
import { preparePhoto } from '../../utils/photo'
import { deviceId } from '../lib'

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
  trunk: 'Main road',
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
  const [photo, setPhoto] = useState<string | null>(null)
  const [photoBusy, setPhotoBusy] = useState(false)
  const cameraRef = useRef<HTMLInputElement>(null)
  const galleryRef = useRef<HTMLInputElement>(null)
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
        // Only ask when nearby candidates are genuinely different paths (e.g. a road and the
        // sidewalk beside it); a junction of similar footpaths is auto-snapped to the nearest.
        const close = found.filter((c) => c.distance_m - found[0].distance_m < 10)
        const kinds = new Set(close.map((c) => `${c.highway}|${c.name ?? ''}`))
        const ambiguous = close.length > 1 && kinds.size > 1
        const options = ambiguous ? close.filter((c, i, all) => all.findIndex((o) => `${o.highway}|${o.name ?? ''}` === `${c.highway}|${c.name ?? ''}`) === i) : []
        setCandidates(options)
        setSegment(ambiguous ? options[0].segment_id : null)
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
      () => setError(t("Couldn't get your location. Tap the map instead.")),
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  const onPhoto = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setPhotoBusy(true)
    setError(null)
    try {
      setPhoto(await preparePhoto(file))
    } catch (err) {
      setError(err instanceof Error ? t(err.message) : t("That photo couldn't be read. Try JPEG or PNG."))
    } finally {
      setPhotoBusy(false)
    }
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!point) return setError(t('Tap the map where the problem is.'))
    if (outside) return setError(t('That spot is outside the area WalkLah covers.'))
    if (!category) return setError(t('Choose what the issue is.'))
    setSubmitting(true)
    try {
      const report = await api.createReport({
        category,
        description: description.trim() || null,
        ...(photo ? { photo } : {}),
        latitude: point.latitude,
        longitude: point.longitude,
        device: deviceId(),
        ...(segment && candidates.length > 0 ? { segment_id: segment } : {}),
      })
      await onSubmitted()
      setSubmitted(report)
      setCategory(null)
      setDescription('')
      setPhoto(null)
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
        <h1 className="go-title">{submitted.merged ? t('Already reported') : t('Report sent')}</h1>
        <div className="success-card" role="status">
          <Icon name="check" size={22} />
          <div>
            {submitted.merged ? (
              <>
                <strong>{t('Someone reported this here already — we added your confirmation.')}</strong>
                <p>
                  {t('{n} walkers say it is still there.', { n: submitted.confirmations.still_there })}{' '}
                  {submitted.community_confirmed && t('Routes now avoid it until an operator checks it.')}
                </p>
              </>
            ) : (
              <>
                <strong>{t("Thanks — it's pending verification.")}</strong>
                <p>
                  {t('When 3 walkers confirm a temporary hazard, routes avoid it until an operator checks it.')}
                  {submitted.temporary_or_permanent === 'temporary' && ` ${t('Temporary issues expire unless someone reconfirms them.')}`}
                </p>
              </>
            )}
            <StatusBadge status={submitted.status} />
          </div>
        </div>
        <div className="button-row">
          <button type="button" className="btn" onClick={onCommunity}>
            {t('Community updates')}
          </button>
          <button type="button" className="btn btn--primary" onClick={() => setSubmitted(null)}>
            {t('Report another')}
          </button>
        </div>
      </div>
    )
  }

  return (
    <form className="go-screen" onSubmit={submit} noValidate>
      <h1 className="go-title">{t('Report an issue')}</h1>

      <div className={`location-card${point ? ' has-point' : ''}${outside ? ' is-invalid' : ''}`}>
        <Icon name="pin" size={20} className="location-card__icon" />
        <div className="location-card__text">
          {point ? (
            <>
              <strong>{outside ? t('Outside the area WalkLah covers') : t('Spot marked')}</strong>
              <span>{t('Drag the pin to adjust')}</span>
            </>
          ) : (
            <>
              <strong>{t('Tap the map where it is')}</strong>
              <span>{t("It's linked to the nearest path")}</span>
            </>
          )}
        </div>
        {point ? (
          <button type="button" className="icon-btn" onClick={() => onPoint(null)} aria-label={t('Clear location')}>
            <Icon name="x" size={18} />
          </button>
        ) : (
          <button type="button" className="btn btn--small" onClick={useMyLocation}>
            {t('Here')}
          </button>
        )}
      </div>

      {point && !outside && candidates.length > 0 && (
        <fieldset className="go-field">
          <legend className="go-label">{t('Which path is it on?')}</legend>
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
                  <strong>{t(HIGHWAY_LABELS[c.highway] ?? 'Path')}</strong>
                  <span>
                    {c.name ? `${c.name} · ` : ''}
                    {t('{d} m from your pin', { d: Math.round(c.distance_m) })}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <fieldset className="go-field">
        <legend className="go-label">{t("What's the issue?")}</legend>
        <div className="category-tiles" role="radiogroup" aria-label={t('Category')}>
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
                {t(c.label)}
                {durationLabel(c.value) && <small>{t(durationLabel(c.value)!)}</small>}
              </span>
            </button>
          ))}
        </div>
      </fieldset>

      <div className="go-field">
        <span className="go-label">
          {t('Photo')} <span className="muted">({t('optional, helps the operator verify')})</span>
        </span>
        {photo ? (
          <div className="photo-preview">
            <img src={photo} alt={t('Your photo')} />
            <button type="button" className="btn btn--small" onClick={() => setPhoto(null)}>
              <Icon name="x" size={16} /> {t('Remove')}
            </button>
          </div>
        ) : (
          <div className="photo-actions">
            <button type="button" className="btn btn--small" onClick={() => cameraRef.current?.click()} disabled={photoBusy}>
              <Icon name="camera" size={16} /> {photoBusy ? t('Preparing…') : t('Take photo')}
            </button>
            <button type="button" className="btn btn--small btn--ghost" onClick={() => galleryRef.current?.click()} disabled={photoBusy}>
              <Icon name="image" size={16} /> {t('Choose photo')}
            </button>
          </div>
        )}
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={(e) => void onPhoto(e)} />
        <input ref={galleryRef} type="file" accept="image/*" hidden onChange={(e) => void onPhoto(e)} />
        <span className="fine-print">{t('Please avoid faces and number plates. Location data is removed from the photo.')}</span>
      </div>

      <label className="go-field">
        <span className="go-label">
          {t('Description')} <span className="muted">({t('optional')})</span>
        </span>
        <textarea
          value={description}
          maxLength={MAX_DESCRIPTION}
          rows={2}
          placeholder={t('What did you see?')}
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
            <span className="spinner" aria-hidden="true" /> {t('Sending…')}
          </>
        ) : (
          <>
            <Icon name="shoe" size={20} className="accent-icon" /> {t('Submit report')}
          </>
        )}
      </button>
      <p className="fine-print center">{t('Reports are anonymous; no name or account is stored.')}</p>
    </form>
  )
}

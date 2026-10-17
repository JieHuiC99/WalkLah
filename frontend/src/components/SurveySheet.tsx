import { useEffect, useRef } from 'react'
import { DATA_BOUNDS } from '../config/map'
import type { Destination } from '../types'
import { Icon } from './icons'
import { StepRail } from './StepRail'

interface Props {
  open: boolean
  destinations: Destination[]
  onClose: () => void
}

/** S · Survey: states plainly what the walking network is, and what has not been surveyed yet. */
export function SurveySheet({ open, destinations, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <section className="survey-sheet" role="dialog" aria-modal="true" aria-labelledby="survey-title" onClick={(e) => e.stopPropagation()}>
        <header className="survey-sheet__head">
          <div>
            <span className="stage-tag">S · Survey</span>
            <h2 id="survey-title">Map data</h2>
          </div>
          <button ref={closeRef} type="button" className="icon-btn" onClick={onClose} aria-label="Close map data">
            <Icon name="x" size={20} />
          </button>
        </header>
        <StepRail current="S" />
        <div className="survey-sheet__items">
          <article className="info-card">
            <Icon name="route" size={20} className="info-card__icon" />
            <div>
              <h3>Walking network</h3>
              <p>
                OpenStreetMap footpaths within about 2 km of Universiti Malaya
                (lat {DATA_BOUNDS.south}–{DATA_BOUNDS.north}, lon {DATA_BOUNDS.west}–{DATA_BOUNDS.east}). Routes follow this
                network.
              </p>
            </div>
          </article>
          <article className="info-card">
            <Icon name="pin" size={20} className="info-card__icon" />
            <div>
              <h3>Places</h3>
              <p>
                {destinations.length > 0
                  ? `${destinations.length} demo places around UM, loaded from the WalkLah server.`
                  : 'Demo places load from the WalkLah server.'}
              </p>
            </div>
          </article>
          <article className="info-card info-card--warning">
            <Icon name="info" size={20} className="info-card__icon" />
            <div>
              <h3>Not yet surveyed in the app</h3>
              <p>
                Sidewalk, crossing, shade and lighting conditions aren't recorded yet. A path with no reports isn't verified
                safe.
              </p>
            </div>
          </article>
        </div>
        <p className="survey-sheet__credit">
          Map data ©{' '}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
            OpenStreetMap contributors
          </a>{' '}
          (ODbL). Map tiles by{' '}
          <a href="https://openfreemap.org" target="_blank" rel="noreferrer">
            OpenFreeMap
          </a>
          .
        </p>
      </section>
    </div>
  )
}

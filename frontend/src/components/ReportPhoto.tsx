import { useEffect, useRef, useState } from 'react'
import { t } from '../go/i18n'
import type { Report } from '../types'
import { photoSrc } from '../utils/photo'
import { Icon } from './icons'

/** Thumbnail of a report's photo; tap to see it full size. Renders nothing without a photo. */
export function ReportPhoto({ report, size = 'small' }: { report: Report; size?: 'small' | 'large' }) {
  const [open, setOpen] = useState(false)
  const [failed, setFailed] = useState(false)
  const src = photoSrc(report.photo_url)
  if (!src || failed) return null
  return (
    <>
      <button
        type="button"
        className={`report-photo report-photo--${size}`}
        onClick={() => setOpen(true)}
        aria-label={t('View photo')}
      >
        <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} />
      </button>
      {open && <PhotoViewer src={src} sample={report.source === 'sample'} onClose={() => setOpen(false)} />}
    </>
  )
}

/** Full-screen photo (Escape or tap to close). */
export function PhotoViewer({ src, sample, onClose }: { src: string; sample?: boolean; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="photo-viewer" role="dialog" aria-modal="true" aria-label={t('Report photo')} onClick={onClose}>
      <img src={src} alt={t('Report photo')} onClick={(e) => e.stopPropagation()} />
      {sample && <p className="photo-viewer__note">{t('Sample photo (openly licensed); see credits in the operator view.')}</p>}
      <button ref={closeRef} type="button" className="photo-viewer__close" onClick={onClose} aria-label={t('Close')}>
        <Icon name="x" size={22} />
      </button>
    </div>
  )
}

/** Grey tag on labelled sample reports, so they are never mistaken for real ones. */
export function SampleTag() {
  return (
    <span className="status-badge status-badge--grey status-badge--small sample-tag" title={t('Example report loaded by an operator')}>
      {t('Sample')}
    </span>
  )
}

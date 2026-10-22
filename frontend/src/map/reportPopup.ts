import { categoryLabel } from '../config/categories'
import { statusMeta } from '../config/status'
import type { Report } from '../types'
import { formatRelative } from '../utils/format'
import { photoSrc } from '../utils/photo'

/** Plain-DOM status badge for map popups (outside React); same classes as StatusBadge. */
function statusBadgeElement(status: string): HTMLElement {
  const meta = statusMeta(status)
  const badge = document.createElement('span')
  badge.className = `status-badge status-badge--${meta.tone} status-badge--small`
  badge.textContent = meta.label
  return badge
}

/** Popup body for a report marker. Built with textContent so report text is never parsed as HTML. */
export function reportPopupContent(report: Report): HTMLElement {
  const root = document.createElement('div')
  root.className = 'report-popup'
  const title = document.createElement('strong')
  title.textContent = categoryLabel(report.category)
  root.append(title)
  const src = photoSrc(report.photo_url)
  if (src) {
    const img = document.createElement('img')
    img.className = 'report-popup__photo'
    img.src = src
    img.alt = ''
    img.loading = 'lazy'
    root.append(img)
  }
  if (report.description) {
    const description = document.createElement('p')
    description.textContent = report.description
    root.append(description)
  }
  const meta = document.createElement('div')
  meta.className = 'report-popup__meta'
  const time = document.createElement('span')
  time.textContent = formatRelative(report.created_at)
  meta.append(statusBadgeElement(report.status), time)
  if (report.source === 'sample') {
    const tag = document.createElement('span')
    tag.className = 'status-badge status-badge--grey status-badge--small'
    tag.textContent = 'Sample'
    meta.append(tag)
  }
  root.append(meta)
  return root
}

import { useEffect, useState } from 'react'
import * as api from '../api/walklahApi'
import { StatusBadge } from '../components/StatusBadge'
import type { SegmentCard } from '../types'
import { t } from './i18n'
import { Sheet } from './Sheet'

const HIGHWAY: Record<string, string> = {
  footway: 'Footpath',
  path: 'Path',
  pedestrian: 'Pedestrian street',
  steps: 'Steps',
  corridor: 'Covered corridor',
  service: 'Service road',
  residential: 'Residential road',
  unclassified: 'Minor road',
  tertiary: 'Road',
  secondary: 'Main road',
  primary: 'Main road',
  trunk: 'Highway',
}

type Known = 'good' | 'bad' | 'unknown' | 'info'

function Row({ label, value, state }: { label: string; value: string; state: Known }) {
  return (
    <div className={`fact fact--${state}`}>
      <span className="fact__label">{label}</span>
      <span className="fact__value">{value}</span>
    </div>
  )
}

/** S · Survey made visible to walkers: what is known about one path, and what isn't. */
export function SegmentSheet({ segmentId, at, onClose }: { segmentId: string; at?: string; onClose: () => void }) {
  const [card, setCard] = useState<SegmentCard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getSegment(segmentId, at).then(
      (c) => !cancelled && setCard(c),
      (e: unknown) => !cancelled && setError(api.errorMessage(e)),
    )
    return () => {
      cancelled = true
    }
  }, [segmentId, at])

  return (
    <Sheet
      title={card?.name ?? t(card ? (HIGHWAY[card.highway] ?? 'Path') : 'Path')}
      kicker={t('About this path')}
      onClose={onClose}
    >
      {error && <p className="inline-error">{error}</p>}
      {!card && !error && (
        <p className="muted">
          <span className="spinner" aria-hidden="true" /> {t('Loading…')}
        </p>
      )}
      {card && (
        <div className="facts">
          <Row label={t('Type')} value={`${t(HIGHWAY[card.highway] ?? card.highway)} · ${Math.round(card.length_m)} m`} state="info" />
          <Row
            label={t('Sidewalk')}
            value={t({ footpath: 'Dedicated footpath', yes: 'Sidewalk mapped', no: 'No sidewalk', unknown: 'Unknown' }[card.sidewalk])}
            state={card.sidewalk === 'unknown' ? 'unknown' : card.sidewalk === 'no' ? 'bad' : 'good'}
          />
          <Row label={t('Steps')} value={t(card.steps ? 'Yes — not step-free' : 'No steps mapped')} state={card.steps ? 'bad' : 'good'} />
          <Row
            label={t('Traffic nearby')}
            value={t({ low: 'Quiet', medium: 'Some traffic', high: 'Busy road', unknown: 'Unknown' }[card.traffic_stress])}
            state={card.traffic_stress === 'high' ? 'bad' : card.traffic_stress === 'unknown' ? 'unknown' : 'good'}
          />
          <Row
            label={t('Shade now')}
            value={card.shade_now_pct === null ? t('After dark') : `${Math.round(card.shade_now_pct)}%`}
            state="info"
          />
          <Row label={t('Tree canopy')} value={t('{pct}% of the path', { pct: Math.round(card.tree_canopy_pct) })} state="info" />
          <Row label={t('Covered')} value={t('{pct}% of the path', { pct: Math.round(card.covered_pct) })} state="info" />
          <Row
            label={t('Lighting')}
            value={
              card.lighting.status === 'unknown'
                ? t('Unknown — not surveyed yet')
                : `${t(card.lighting.status === 'yes' ? 'Lit' : 'Not lit')} (${t(
                    { audit: 'team audit', osm_tag: 'OpenStreetMap', osm_lamp: 'street lamp mapped' }[card.lighting.source ?? 'osm_tag'],
                  )})`
            }
            state={card.lighting.status === 'unknown' ? 'unknown' : card.lighting.status === 'yes' ? 'good' : 'bad'}
          />
          {card.crossings.length > 0 && (
            <Row label={t('Crossings')} value={card.crossings.map((c) => t(c.type)).join(', ')} state="info" />
          )}
          {card.reports.length > 0 && (
            <div className="facts__reports">
              {card.reports.map((r) => (
                <StatusBadge key={r.id} status={r.status} size="small" />
              ))}
            </div>
          )}
          <p className="fine-print">{t("Unknown means nobody has checked yet — not that it's fine.")}</p>
        </div>
      )}
    </Sheet>
  )
}

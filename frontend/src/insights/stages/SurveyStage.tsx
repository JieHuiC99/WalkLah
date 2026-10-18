import { useEffect, useState, type ChangeEvent } from 'react'
import * as api from '../../api/walklahApi'
import { Icon } from '../../components/icons'
import type { AuditRow } from '../../types'
import type { StageProps } from '../InsightsApp'
import { StageHeader } from './StageHeader'

/** Minimal CSV reader for the audit template (no quoted commas expected). */
function parseCsv(text: string): { rows: AuditRow[]; problems: string[] } {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
  const problems: string[] = []
  if (lines.length < 2) return { rows: [], problems: ['The file has no data rows.'] }
  const header = lines[0].split(',').map((h) => h.trim().toLowerCase())
  const col = (name: string) => header.indexOf(name)
  if (col('segment_id') < 0 || col('checked_at') < 0) {
    return { rows: [], problems: ['Header must include segment_id and checked_at (download the template).'] }
  }
  const rows: AuditRow[] = []
  lines.slice(1).forEach((line, i) => {
    const cells = line.split(',').map((c) => c.trim())
    const get = (name: string) => (col(name) >= 0 ? cells[col(name)] || null : null)
    const lit = get('lit')
    const sidewalk = get('sidewalk')
    if (lit && !['yes', 'no'].includes(lit)) problems.push(`Row ${i + 2}: lit must be yes or no`)
    if (sidewalk && !['yes', 'no', 'footpath'].includes(sidewalk)) problems.push(`Row ${i + 2}: sidewalk must be yes, no or footpath`)
    rows.push({
      segment_id: get('segment_id') ?? '',
      lit: (lit as AuditRow['lit']) ?? null,
      sidewalk: (sidewalk as AuditRow['sidewalk']) ?? null,
      checked_at: get('checked_at') ?? '',
      auditor: get('auditor'),
      note: get('note'),
    })
  })
  return { rows, problems }
}

export function SurveyStage({ operatorKey, overview, refresh }: StageProps) {
  const [audit, setAudit] = useState<AuditRow[]>([])
  const [pending, setPending] = useState<{ rows: AuditRow[]; problems: string[]; file: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getAudit(operatorKey).then((rows) => !cancelled && setAudit(rows), () => undefined)
    return () => {
      cancelled = true
    }
  }, [operatorKey])

  const c = overview?.survey.coverage
  const a = overview?.survey.audited_coverage
  const national = c && c.lighting_tagged_pct !== undefined
  const tiles: [string, number | null | undefined, string][] = c
    ? national
      ? [
          ['Sidewalk status known', c.sidewalk_known_pct, 'Dedicated footpaths or mapped sidewalks (OSM)'],
          ['Lighting tagged', c.lighting_tagged_pct, 'OSM lit tags; street lamps add more per area'],
          ['Covered ways tagged', c.covered_tagged_pct, 'Covered, arcade, corridor or tunnel'],
          ['Dedicated footpaths', c.dedicated_footpath_pct, 'Of all walkable path length'],
          ['Real building heights', c.building_heights_real_pct, 'Others estimated at 9 m'],
        ]
      : [
          ['Sidewalk status known', c.sidewalk_known_pct, 'Dedicated footpaths or mapped sidewalks'],
          ['Lighting known', c.lighting_known_pct, 'Team audit, OSM lit tags or lamps'],
          ['Under tree canopy', c.canopy_pct, 'Meta/WRI 1 m canopy ≥ 3 m'],
          ['Covered walkways', c.covered_pct, 'Roofs, shelters, covered ways'],
          ['Real building heights', c.building_heights_real_pct, 'Others estimated at 9 m'],
          ['Steps', c.steps_pct, 'Of path length'],
        ]
    : []
  const auditedTiles: [string, number | null | undefined, string][] =
    national && a
      ? [
          ['Lighting known', a.lighting_known_pct, 'Team audit, OSM lit tags or lamps'],
          ['Under tree canopy', a.canopy_pct, 'Meta/WRI 1 m canopy ≥ 3 m'],
          ['Covered walkways', a.covered_pct, 'Roofs, shelters, covered ways'],
          ['Sidewalk status known', a.sidewalk_known_pct, 'Dedicated footpaths or mapped sidewalks'],
        ]
      : []

  const downloadTemplate = async () => {
    const text = await api.auditTemplate()
    const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'walklah-audit-template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setMessage(null)
    setPending({ ...parseCsv(await file.text()), file: file.name })
  }

  const upload = async () => {
    if (!pending) return
    setBusy(true)
    try {
      const result = await api.uploadAudit(operatorKey, pending.rows)
      setMessage({ ok: true, text: `Saved ${result.saved} rows · ${result.audited_segments} segments audited in total.` })
      setPending(null)
      setAudit(await api.getAudit(operatorKey))
      await refresh()
    } catch (e) {
      setMessage({ ok: false, text: api.errorMessage(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stage">
      <StageHeader
        letter="S"
        title="Survey"
        lead="What the walking map knows — and what still needs checking on foot."
      />

      {national && <h2 className="stage-subhead">Malaysia · OpenStreetMap</h2>}
      <TileGrid tiles={tiles} />
      {c && (
        <p className="muted small">
          {c.segments.toLocaleString('en-MY')} path segments · {Math.round(c.network_km).toLocaleString('en-MY')} km mapped ·{' '}
          {c.buildings.toLocaleString('en-MY')} buildings · {c.places.toLocaleString('en-MY')} places ·{' '}
          {c.audited_segments ?? 0} segments audited by the team.
        </p>
      )}
      {auditedTiles.length > 0 && (
        <>
          <h2 className="stage-subhead">Team-audited area · Universiti Malaya</h2>
          <TileGrid tiles={auditedTiles} />
          <p className="muted small">
            Tree canopy is measured everywhere at 10 m (ESA WorldCover) and at 1 m around UM (Meta/WRI). Audit more areas to
            turn "unknown" into evidence.
          </p>
        </>
      )}

      <section className="card">
        <h2>Field audit</h2>
        <p className="muted small">
          Walk the corridors, record lighting and sidewalks per path segment, then upload the CSV. Audits override
          OpenStreetMap values straight away. Proposal target: 30–50 segments.
        </p>
        <div className="button-row button-row--start">
          <button type="button" className="btn btn--small" onClick={() => void downloadTemplate()}>
            <Icon name="download" size={16} /> CSV template
          </button>
          <label className="btn btn--small btn--dark file-button">
            <Icon name="upload" size={16} /> Choose CSV…
            <input type="file" accept=".csv,text/csv" onChange={(e) => void onFile(e)} />
          </label>
        </div>
        <p className="muted small">Tip: tap a path in WalkLah Go to see its segment ID.</p>
        {pending && (
          <div className="upload-preview">
            <strong>
              {pending.file}: {pending.rows.length} rows
            </strong>
            {pending.problems.length > 0 ? (
              <ul className="problem-list">
                {pending.problems.slice(0, 5).map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            ) : (
              <button type="button" className="btn btn--small btn--primary" onClick={() => void upload()} disabled={busy}>
                {busy ? 'Uploading…' : 'Upload audit'}
              </button>
            )}
          </div>
        )}
        {message && <p className={message.ok ? 'ok-note' : 'inline-error'}>{message.text}</p>}
        {audit.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Segment</th>
                <th>Lit</th>
                <th>Sidewalk</th>
                <th>Checked</th>
                <th>By</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((row) => (
                <tr key={row.segment_id}>
                  <td className="mono">{row.segment_id}</td>
                  <td>{row.lit ?? '—'}</td>
                  <td>{row.sidewalk ?? '—'}</td>
                  <td>{row.checked_at}</td>
                  <td>{row.auditor ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card card--quiet">
        <h2>Sources</h2>
        <ul className="source-list">
          {(overview?.survey.sources ?? []).map((s) => (
            <li key={s}>{s}</li>
          ))}
          <li>Sun position: NOAA solar equations · Weather (walker app): Open-Meteo.com</li>
        </ul>
        {overview?.survey.built_at && <p className="muted small">Layer built {overview.survey.built_at.slice(0, 10)}.</p>}
      </section>
    </div>
  )
}

function TileGrid({ tiles }: { tiles: [string, number | null | undefined, string][] }) {
  return (
    <div className="tile-grid">
      {tiles.map(([label, value, hint]) => (
        <div key={label} className={`tile${(value ?? 0) < 20 ? ' tile--low' : ''}`}>
          <span className="tile__value">{value === null || value === undefined ? '—' : `${Math.round(value)}%`}</span>
          <span className="tile__label">{label}</span>
          <span className="tile__hint">{hint}</span>
        </div>
      ))}
    </div>
  )
}

import { Icon, type IconName } from '../components/icons'
import type { Pilot } from '../types'
import type { GoPrefs } from './lib'
import { Sheet } from './Sheet'

const HOW: { icon: IconName; title: string; text: string }[] = [
  { icon: 'map', title: 'We map the paths', text: 'OpenStreetMap paths, tree canopy, shade and on-foot checks by our team.' },
  { icon: 'flag', title: 'You report what changed', text: 'Blocked, flooded or unlit? Other walkers confirm it.' },
  { icon: 'route', title: 'Routes work around it', text: 'Verified obstacles are avoided; shade and lighting shape the comfy route.' },
  { icon: 'chart', title: 'The township fixes it', text: 'Operators see which problems cost walkers the most and plan repairs.' },
]

export function AboutSheet({
  pilot,
  prefs,
  onPrefs,
  onClose,
}: {
  pilot: Pilot | null
  prefs: GoPrefs
  onPrefs: (p: GoPrefs) => void
  onClose: () => void
}) {
  const c = pilot?.coverage
  return (
    <Sheet title="How WalkLah works" onClose={onClose} tall>
      <ol className="how-list">
        {HOW.map((step) => (
          <li key={step.title}>
            <span className="how-list__icon">
              <Icon name={step.icon} size={18} />
            </span>
            <span>
              <strong>{step.title}</strong>
              <span>{step.text}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="fine-print">This is our S.T.E.P. framework: Survey, Track, Explore, Prioritise.</p>

      {c && (
        <section className="about-section">
          <h3>What the map knows today</h3>
          <div className="coverage-grid">
            <div>
              <strong>{Math.round(c.canopy_pct ?? c.green_pct)}%</strong>
              <span>of paths under trees</span>
            </div>
            <div>
              <strong>{Math.round(c.covered_pct)}%</strong>
              <span>covered walkways</span>
            </div>
            <div>
              <strong>{Math.round(c.sidewalk_known_pct)}%</strong>
              <span>sidewalk status known</span>
            </div>
            <div>
              <strong>{Math.round(c.lighting_known_pct)}%</strong>
              <span>lighting known</span>
            </div>
          </div>
          <p className="fine-print">
            Everything else is shown as unknown, not as fine. Pilot area: {pilot?.radius_m.toLocaleString('en-MY')} m around{' '}
            {pilot?.anchor.name}.
          </p>
        </section>
      )}

      <section className="about-section">
        <h3>Your settings</h3>
        <label className="toggle-row">
          <input type="checkbox" checked={prefs.stepFree} onChange={(e) => onPrefs({ ...prefs, stepFree: e.target.checked })} />
          <span className="toggle-row__switch" aria-hidden="true" />
          <span className="toggle-row__text">
            <strong>Step-free routes</strong>
            <span>Avoid stairs</span>
          </span>
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={prefs.shareStats}
            onChange={(e) => onPrefs({ ...prefs, shareStats: e.target.checked })}
          />
          <span className="toggle-row__switch" aria-hidden="true" />
          <span className="toggle-row__text">
            <strong>Share anonymous route stats</strong>
            <span>Helps the township see which problems cost walkers time. No locations or identity are stored.</span>
          </span>
        </label>
      </section>

      <section className="about-section about-section--credits">
        <h3>Data</h3>
        <p>
          Map data © OpenStreetMap contributors (ODbL) · tiles OpenFreeMap / OpenMapTiles · tree canopy: Meta & World
          Resources Institute, Global Canopy Height (CC BY 4.0), imagery © Maxar · weather: Open-Meteo.com (CC BY 4.0) ·
          sun position: NOAA equations.
        </p>
        <p>
          WalkLah gives comfort estimates, not safety guarantees. <a href="?app=insights">For township operators →</a>
        </p>
      </section>
    </Sheet>
  )
}

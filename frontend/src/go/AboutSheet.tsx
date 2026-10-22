import { Icon, type IconName } from '../components/icons'
import type { Pilot, RainMode } from '../types'
import { t } from './i18n'
import type { GoPrefs } from './lib'
import { Sheet } from './Sheet'

const HOW: { icon: IconName; title: string; text: string }[] = [
  { icon: 'map', title: 'We map the paths', text: 'OpenStreetMap paths, tree canopy, shade and on-foot checks by our team.' },
  { icon: 'flag', title: 'You report what changed', text: 'Blocked, flooded or unlit? Other walkers confirm it.' },
  { icon: 'route', title: 'Routes work around it', text: 'Confirmed obstacles are avoided; shade, lighting and rain cover shape the comfy route.' },
  { icon: 'chart', title: 'The township fixes it', text: 'Operators see which problems cost walkers the most and plan repairs.' },
]

const pct = (value: number | null | undefined) => (value === null || value === undefined ? '—' : `${Math.round(value)}%`)

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
  const cities = pilot?.covered_areas?.map((area) => area.name) ?? []
  // Nationwide figures only when the whole country is routable (not on the city-only service).
  const national = pilot?.coverage_area === 'malaysia' && !cities.length ? pilot.coverage : null
  const audited = pilot?.audited_coverage
  return (
    <Sheet title={t('How WalkLah works')} onClose={onClose} tall>
      <ol className="how-list">
        {HOW.map((step) => (
          <li key={step.title}>
            <span className="how-list__icon">
              <Icon name={step.icon} size={18} />
            </span>
            <span>
              <strong>{t(step.title)}</strong>
              <span>{t(step.text)}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="fine-print">{t('This is our S.T.E.P. framework: Survey, Track, Explore, Prioritise.')}</p>

      {pilot && (
        <section className="about-section">
          <h3>{t('What the map knows today')}</h3>
          {cities.length > 0 && <p>{t('Walking routes and search cover {cities}.', { cities: cities.join(', ') })}</p>}
          {national && (
            <div className="coverage-grid">
              <div>
                <strong>{Math.round(national.network_km).toLocaleString('en-MY')} km</strong>
                <span>{t('of walkable paths in Malaysia')}</span>
              </div>
              <div>
                <strong>{national.places.toLocaleString('en-MY')}</strong>
                <span>{t('places to search')}</span>
              </div>
              <div>
                <strong>{pct(national.sidewalk_known_pct)}</strong>
                <span>{t('sidewalk status known')}</span>
              </div>
              <div>
                <strong>{pct(national.lighting_tagged_pct ?? national.lighting_known_pct)}</strong>
                <span>{t('lighting tagged')}</span>
              </div>
            </div>
          )}
          {audited && (
            <>
              <h4 className="about-subhead">
                {t('Team-audited area')} · {pilot.audited_area.anchor.name}
              </h4>
              <div className="coverage-grid">
                <div>
                  <strong>{pct(audited.canopy_pct ?? audited.green_pct)}</strong>
                  <span>{t('of paths under trees')}</span>
                </div>
                <div>
                  <strong>{pct(audited.covered_pct)}</strong>
                  <span>{t('covered walkways')}</span>
                </div>
                <div>
                  <strong>{pct(audited.sidewalk_known_pct)}</strong>
                  <span>{t('sidewalk status known')}</span>
                </div>
                <div>
                  <strong>{pct(audited.lighting_known_pct)}</strong>
                  <span>{t('lighting known')}</span>
                </div>
              </div>
            </>
          )}
          <p className="fine-print">{t('Everything else is shown as unknown, not as fine.')}</p>
        </section>
      )}

      <section className="about-section">
        <h3>{t('Your settings')}</h3>
        <div className="settings-row">
          <span>
            <Icon name="globe" size={16} /> {t('Language')}
          </span>
          <div className="segmented segmented--two" role="radiogroup" aria-label={t('Language')}>
            {(['en', 'ms'] as const).map((lang) => (
              <button
                key={lang}
                type="button"
                role="radio"
                aria-checked={prefs.lang === lang}
                className={prefs.lang === lang ? 'is-active' : ''}
                onClick={() => onPrefs({ ...prefs, lang })}
              >
                {lang === 'en' ? 'English' : 'Bahasa Melayu'}
              </button>
            ))}
          </div>
        </div>
        <div className="settings-row">
          <span>
            <Icon name="umbrella" size={16} /> {t('Rain cover')}
          </span>
          <div className="segmented segmented--three" role="radiogroup" aria-label={t('Rain cover')}>
            {(['auto', 'on', 'off'] as RainMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                role="radio"
                aria-checked={prefs.rain === mode}
                className={prefs.rain === mode ? 'is-active' : ''}
                onClick={() => onPrefs({ ...prefs, rain: mode })}
              >
                {t({ auto: 'Auto', on: 'On', off: 'Off' }[mode])}
              </button>
            ))}
          </div>
        </div>
        <label className="toggle-row">
          <input type="checkbox" checked={prefs.stepFree} onChange={(e) => onPrefs({ ...prefs, stepFree: e.target.checked })} />
          <span className="toggle-row__switch" aria-hidden="true" />
          <span className="toggle-row__text">
            <strong>{t('Step-free routes')}</strong>
            <span>{t('Avoid stairs')}</span>
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
            <strong>{t('Share anonymous route stats')}</strong>
            <span>
              {t('Helps the township see which problems cost walkers time. Only distances and a ~1 km area are stored, never your exact route or identity.')}
            </span>
          </span>
        </label>
      </section>

      <section className="about-section about-section--credits">
        <h3>{t('Data')}</h3>
        <p>
          Map data © OpenStreetMap contributors (ODbL) · places: Overture Maps Foundation (CDLA-Permissive-2.0) · tiles
          OpenFreeMap / OpenMapTiles · tree canopy: Meta & World Resources Institute, Global Canopy Height (CC BY 4.0),
          imagery © Maxar; ESA WorldCover 10 m 2021 (CC BY 4.0) · weather: Open-Meteo.com (CC BY 4.0) · sun position:
          NOAA equations.
        </p>
        <p>
          {t('WalkLah gives comfort estimates, not safety guarantees.')}{' '}
          <a href="?app=insights">{t('For township operators →')}</a>
        </p>
      </section>
    </Sheet>
  )
}

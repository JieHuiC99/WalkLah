import { Icon } from '../../components/icons'
import { t } from '../i18n'
import { greeting, type GoPrefs } from '../lib'
import { TripCard } from '../TripCard'
import type { Endpoint } from '../types'

interface Props {
  from: Endpoint | null
  to: Endpoint | null
  prefs: GoPrefs
  onPrefs: (prefs: GoPrefs) => void
  onOpenPicker: (which: 'from' | 'to') => void
  onSwap: () => void
  onFindRoutes: () => void
  onAbout: () => void
}

export function HomeScreen({ from, to, prefs, onPrefs, onOpenPicker, onSwap, onFindRoutes, onAbout }: Props) {
  const canRoute = Boolean(from && to)
  return (
    <div className="go-home">
      <header className="home-hero">
        <Skyline />
        <div className="home-hero__brand">
          <span className="brand-tile">
            <Icon name="walk" size={22} />
          </span>
          <span className="brand-name">
            <span>
              Walk<em>Lah</em>
            </span>
          </span>
          <button
            type="button"
            className="lang-toggle"
            onClick={() => onPrefs({ ...prefs, lang: prefs.lang === 'ms' ? 'en' : 'ms' })}
            aria-label={prefs.lang === 'ms' ? 'Switch to English' : 'Tukar ke Bahasa Melayu'}
          >
            <Icon name="globe" size={14} /> {prefs.lang === 'ms' ? 'EN' : 'BM'}
          </button>
        </div>
        <p className="home-hero__script" aria-hidden="true">
          Jom
          <br />
          jalan lah!
        </p>
        <h1 className="home-hero__title">{greeting()}</h1>
        <p className="home-hero__tagline">{t('Know what a walk is like before you start it.')}</p>
      </header>

      <div className="go-home__body">
        <div className="home__trip">
          <TripCard from={from} to={to} onOpenPicker={onOpenPicker} onSwap={onSwap} />
        </div>

        <section aria-labelledby="walker-type">
          <h2 id="walker-type" className="go-label">
            {t("I'm walking…")}
          </h2>
          <div className="walker-type" role="radiogroup" aria-label={t('Walking purpose')}>
            <button
              type="button"
              role="radio"
              aria-checked={prefs.walker !== 'leisure'}
              className={prefs.walker !== 'leisure' ? 'is-active' : ''}
              onClick={() => onPrefs({ ...prefs, walker: 'commute' })}
            >
              <Icon name="train" size={20} />
              <strong>{t('To get somewhere')}</strong>
              <span>{t('Reliable, fewer surprises')}</span>
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={prefs.walker === 'leisure'}
              className={prefs.walker === 'leisure' ? 'is-active' : ''}
              onClick={() => onPrefs({ ...prefs, walker: 'leisure' })}
            >
              <Icon name="leaf" size={20} />
              <strong>{t('For the walk')}</strong>
              <span>{t('Shade, green, quiet')}</span>
            </button>
          </div>
        </section>

        <label className="toggle-row">
          <input
            type="checkbox"
            checked={prefs.stepFree}
            onChange={(e) => onPrefs({ ...prefs, stepFree: e.target.checked })}
          />
          <span className="toggle-row__switch" aria-hidden="true" />
          <span className="toggle-row__text">
            <strong>{t('Step-free')}</strong>
            <span>{t('Avoid stairs (wheelchairs, prams, luggage)')}</span>
          </span>
          <Icon name="wheelchair" size={20} />
        </label>

        <button type="button" className="btn btn--primary btn--block btn--large" disabled={!canRoute} onClick={onFindRoutes}>
          {t('Find routes')} <Icon name="arrowRight" size={20} className="accent-icon" />
        </button>

        <button type="button" className="about-link" onClick={onAbout}>
          <Icon name="info" size={16} /> {t('How WalkLah works')}
        </button>
      </div>
    </div>
  )
}

/** Decorative KL skyline with a dotted walking path. */
function Skyline() {
  return (
    <svg className="home-hero__skyline" viewBox="0 0 400 220" preserveAspectRatio="xMaxYMax slice" aria-hidden="true">
      <g fill="currentColor">
        <rect x="200" y="120" width="18" height="100" />
        <rect x="222" y="95" width="12" height="125" />
        <path d="M244 220V92l7-34 7 34v128z" />
        <path d="M266 220V92l7-34 7 34v128z" />
        <rect x="244" y="118" width="36" height="4" />
        <rect x="290" y="132" width="22" height="88" />
        <path d="M326 220V128h5V82h3V48h3v34h3v46h5v92z" />
        <rect x="352" y="140" width="26" height="80" />
        <rect x="382" y="118" width="18" height="102" />
      </g>
      <path className="home-hero__path" d="M10 210C90 176 140 206 210 182S340 160 400 172" fill="none" strokeLinecap="round" />
    </svg>
  )
}

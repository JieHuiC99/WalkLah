import type { ReactNode } from 'react'
import { Icon } from '../components/icons'
import { t } from './i18n'

/**
 * WalkLah Go is a phone app. On a laptop or projector it is shown inside a phone frame;
 * on a real phone (≤ 500 px wide) the frame disappears and the app fills the screen.
 */
export function DeviceFrame({ children }: { children: ReactNode }) {
  return (
    <div className="device-stage">
      <aside className="device-side" aria-label={t('About WalkLah Go')}>
        <div className="device-side__brand">
          <span className="brand-tile">
            <Icon name="walk" size={22} />
          </span>
          <span className="device-side__name">
            Walk<em>Lah</em> <span>Go</span>
          </span>
        </div>
        <p className="device-side__lead">{t('Know what a walk is like before you start it — anywhere in Malaysia.')}</p>
        <ul className="device-side__list">
          <li>
            <Icon name="route" size={18} /> {t('Shortest, Practical and Enjoyable routes between any two places')}
          </li>
          <li>
            <Icon name="sun" size={18} /> {t('Shade by time of day, lighting after dark, cover when it rains')}
          </li>
          <li>
            <Icon name="navigation" size={18} /> {t('Walk mode with turn-by-turn steps and heads-ups')}
          </li>
          <li>
            <Icon name="flag" size={18} /> {t('Hazards reported and confirmed by other walkers')}
          </li>
        </ul>
        <a className="device-side__link" href="?app=insights">
          {t('WalkLah Insights for township operators')} <Icon name="arrowRight" size={16} />
        </a>
        <p className="device-side__note">{t('Open this page on your phone to use it full-screen, or install it to your home screen.')}</p>
      </aside>
      <div className="device">
        <div className="device__notch" aria-hidden="true" />
        <div className="device__screen">{children}</div>
      </div>
    </div>
  )
}

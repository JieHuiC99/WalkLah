import { useEffect, useState, type ReactNode } from 'react'
import { Icon } from '../components/icons'
import { t } from './i18n'

const PHONE_W = 414 // 390 px screen + bezel
const PHONE_H = 868 // 844 px screen + bezel
const MIN_SCALE = 0.55

/** How much to shrink the phone so it fits the window (1 = actual size). */
function frameScale(): number {
  const w = window.innerWidth
  const h = window.innerHeight
  if (w <= 500) return 1 // real phone: no frame
  const sideWidth = w > 900 ? 300 + 48 : 0 // the description panel beside the phone
  const byHeight = (h - 32) / PHONE_H
  const byWidth = (w - 40 - sideWidth) / PHONE_W
  return Math.max(MIN_SCALE, Math.min(1, byHeight, byWidth))
}

/**
 * The WalkLah walker view is a phone app. On a laptop or projector it is shown inside a phone frame that is
 * always laid out at real phone size and scaled as a whole to fit the window (small laptops,
 * browser zoom, projectors). On a real phone (≤ 500 px wide) the frame disappears.
 */
export function DeviceFrame({ children }: { children: ReactNode }) {
  const [scale, setScale] = useState(frameScale)
  useEffect(() => {
    const onResize = () => setScale(frameScale())
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  return (
    <div className="device-stage">
      <aside className="device-side" aria-label={t('About WalkLah')}>
        <div className="device-side__brand">
          <span className="brand-tile">
            <Icon name="walk" size={22} />
          </span>
          <span className="device-side__name">
            Walk<em>Lah</em>
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
          {t('For township operators')} <Icon name="arrowRight" size={16} />
        </a>
        <p className="device-side__note">{t('Open this page on your phone to use it full-screen, or install it to your home screen.')}</p>
      </aside>
      <div className="device" style={{ zoom: scale }}>
        <div className="device__notch" aria-hidden="true" />
        <div className="device__screen">{children}</div>
      </div>
    </div>
  )
}

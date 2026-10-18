import type { ReactNode } from 'react'
import { Icon } from '../components/icons'

/**
 * WalkLah Go is a phone app. On a laptop or projector it is shown inside a phone frame;
 * on a real phone (≤ 500 px wide) the frame disappears and the app fills the screen.
 */
export function DeviceFrame({ children }: { children: ReactNode }) {
  return (
    <div className="device-stage">
      <aside className="device-side" aria-label="About this demo">
        <div className="device-side__brand">
          <span className="brand-tile">
            <Icon name="walk" size={22} />
          </span>
          <span className="device-side__name">
            Walk<em>Lah</em> <span>Go</span>
          </span>
        </div>
        <p className="device-side__lead">The walker app — shown as it looks on a phone.</p>
        <ul className="device-side__list">
          <li>
            <Icon name="route" size={18} /> Routes between any two points, compared three ways
          </li>
          <li>
            <Icon name="sun" size={18} /> Shade by time of day; lighting after dark
          </li>
          <li>
            <Icon name="flag" size={18} /> Reports, confirmed by other walkers
          </li>
        </ul>
        <a className="device-side__link" href="?app=insights">
          Open WalkLah Insights (operators) <Icon name="arrowRight" size={16} />
        </a>
        <p className="device-side__note">On a phone this opens full-screen.</p>
      </aside>
      <div className="device">
        <div className="device__notch" aria-hidden="true" />
        <div className="device__screen">{children}</div>
      </div>
    </div>
  )
}

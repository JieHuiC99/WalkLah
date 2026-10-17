import type { StepStage } from '../app/navigation'
import { Icon, type IconName } from '../components/icons'
import { TripCard } from '../components/TripCard'
import type { Destination } from '../types'

const STEP_TILES: { stage: StepStage; name: string; hint: string; icon: IconName }[] = [
  { stage: 'S', name: 'Survey', hint: 'Map data', icon: 'map' },
  { stage: 'T', name: 'Track', hint: 'Report issues', icon: 'flag' },
  { stage: 'E', name: 'Explore', hint: 'Compare routes', icon: 'route' },
  { stage: 'P', name: 'Prioritise', hint: 'Operator view', icon: 'chart' },
]

interface Props {
  destinations: Destination[]
  from: string | null
  to: string | null
  onFromChange: (id: string | null) => void
  onToChange: (id: string | null) => void
  onSwap: () => void
  onFindRoute: () => void
  onStage: (stage: StepStage) => void
}

function greeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning!'
  if (hour < 18) return 'Good afternoon!'
  return 'Good evening!'
}

export function HomePage({ destinations, from, to, onFromChange, onToChange, onSwap, onFindRoute, onStage }: Props) {
  const canRoute = Boolean(from && to && from !== to)
  return (
    <div className="home">
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
            <small>Waze for Walking</small>
          </span>
        </div>
        <h1 className="home-hero__title">{greeting()}</h1>
        <p className="home-hero__tagline">Walk around what's blocked, not into it.</p>
        <p className="home-hero__script" aria-hidden="true">
          Jom
          <br />
          jalan lah!
        </p>
      </header>

      <div className="home__trip">
        <TripCard
          destinations={destinations}
          from={from}
          to={to}
          onFromChange={onFromChange}
          onToChange={onToChange}
          onSwap={onSwap}
        />
      </div>

      <section className="home__step" aria-labelledby="step-heading">
        <div className="section-head">
          <h2 id="step-heading">The S.T.E.P. way</h2>
          <span className="muted small">How WalkLah works</span>
        </div>
        <div className="step-tiles">
          {STEP_TILES.map((tile) => (
            <button key={tile.stage} type="button" className={`step-tile step-tile--${tile.stage}`} onClick={() => onStage(tile.stage)}>
              <span className="step-tile__letter">{tile.stage}</span>
              <span className="step-tile__name">{tile.name}</span>
              <span className="step-tile__hint">{tile.hint}</span>
              <Icon name={tile.icon} size={20} className="step-tile__icon" />
            </button>
          ))}
        </div>
      </section>

      <button type="button" className="btn btn--primary btn--block btn--large" disabled={!canRoute} onClick={onFindRoute}>
        Find route <Icon name="arrowRight" size={20} className="accent-icon" />
      </button>
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

import type { StepStage } from '../app/navigation'
import { Icon } from '../components/icons'
import { ScreenHeader } from '../components/ScreenHeader'
import { TripCard } from '../components/TripCard'
import type { RoutesState } from '../hooks/useRoutes'
import type { Destination, RouteResponse } from '../types'
import { formatMetres, formatMinutes, formatSigned } from '../utils/format'

interface Props {
  destinations: Destination[]
  from: string | null
  to: string | null
  onFromChange: (id: string | null) => void
  onToChange: (id: string | null) => void
  onSwap: () => void
  routes: RoutesState
  focus: 'baseline' | 'walklah'
  onFocus: (focus: 'baseline' | 'walklah') => void
  reportCount: number
  onOpenCommunity: () => void
  onStage: (stage: StepStage) => void
}

export function NavigatePage(props: Props) {
  const { destinations, from, to, routes, reportCount, onOpenCommunity, onStage } = props
  const fromName = destinations.find((d) => d.id === from)?.name
  const toName = destinations.find((d) => d.id === to)?.name

  return (
    <div className="navigate">
      <ScreenHeader
        title={toName ? `To ${toName}` : 'Route options'}
        subtitle={fromName ? `From ${fromName}` : 'Choose where you are walking'}
        stage="E"
        onStage={onStage}
      />
      <TripCard
        compact
        destinations={destinations}
        from={from}
        to={to}
        onFromChange={props.onFromChange}
        onToChange={props.onToChange}
        onSwap={props.onSwap}
      />

      <RouteResults {...props} />

      <button type="button" className="community-strip" onClick={onOpenCommunity}>
        <Icon name="message" size={20} className="community-strip__icon" />
        <span className="community-strip__text">
          <strong>
            {reportCount} community {reportCount === 1 ? 'report' : 'reports'} in this area
          </strong>
          <span>See what others have reported</span>
        </span>
        <Icon name="chevronRight" size={18} />
      </button>

      <p className="fine-print">
        Distances follow OpenStreetMap footpaths; times assume a 1.2 m/s walking pace.
        {routes.status === 'idle' ? '' : ' Routes are calculated from mapped paths, not a guarantee the walk is safe.'}
      </p>
    </div>
  )
}

function RouteResults({ from, to, routes, focus, onFocus }: Props) {
  if (!from || !to) {
    return <p className="empty-note">Choose a start and a destination to compare routes.</p>
  }
  if (from === to) {
    return <p className="inline-error">Start and destination must be different places.</p>
  }
  if (routes.status === 'idle') {
    return <p className="empty-note">Routes appear once the WalkLah server is reachable.</p>
  }
  if (routes.status === 'loading') {
    return (
      <div className="loading-card" role="status">
        <span className="spinner" aria-hidden="true" />
        <div>
          <strong>Calculating walking route…</strong>
          <span>The first route can take a few seconds while the map data loads.</span>
        </div>
      </div>
    )
  }

  const { baseline, walklah, baselineError, walklahError, walklahBlocked } = routes.routes
  if (!baseline) {
    return (
      <p className="inline-error" role="alert">
        {baselineError ?? 'No pedestrian route found.'}
      </p>
    )
  }

  const affected = walklah?.affected_segment_ids.length ?? 0
  const recommended = Boolean(walklah && affected > 0)
  const longest = Math.max(baseline.distance_m, walklah?.distance_m ?? 0)

  return (
    <section className="route-results" aria-label="Route comparison">
      <div className="route-cards">
        <RouteCard
          kind="baseline"
          route={baseline}
          selected={focus === 'baseline'}
          onSelect={() => onFocus('baseline')}
        />
        {walklah ? (
          <RouteCard
            kind="walklah"
            route={walklah}
            baseline={baseline}
            recommended={recommended}
            selected={focus === 'walklah'}
            onSelect={() => onFocus('walklah')}
          />
        ) : (
          <div className="route-card route-card--missing" role="alert">
            <span className="route-card__label">WalkLah route</span>
            <p>
              {walklahBlocked
                ? 'No walkable alternative — verified obstacles block every path.'
                : (walklahError ?? 'No WalkLah route available.')}
            </p>
          </div>
        )}
      </div>

      <div className="distance-bars" aria-hidden="true">
        <DistanceBar label="Usual" metres={baseline.distance_m} longest={longest} tone="grey" />
        {walklah && <DistanceBar label="WalkLah" metres={walklah.distance_m} longest={longest} tone="green" />}
      </div>

      {walklah && (
        <p className={`route-status ${affected > 0 ? 'route-status--avoiding' : 'route-status--clear'}`}>
          <Icon name={affected > 0 ? 'shield' : 'check'} size={18} />
          {affected > 0
            ? `Avoiding ${affected} verified ${affected === 1 ? 'obstacle' : 'obstacles'} on the usual path`
            : 'No verified obstacles on this route — WalkLah follows the usual path.'}
        </p>
      )}
    </section>
  )
}

interface RouteCardProps {
  kind: 'baseline' | 'walklah'
  route: RouteResponse
  baseline?: RouteResponse
  recommended?: boolean
  selected: boolean
  onSelect: () => void
}

function RouteCard({ kind, route, baseline, recommended = false, selected, onSelect }: RouteCardProps) {
  const extraMetres = baseline ? route.distance_m - baseline.distance_m : 0
  const extraMinutes = baseline ? route.estimated_minutes - baseline.estimated_minutes : 0
  return (
    <button
      type="button"
      className={`route-card route-card--${kind}${selected ? ' is-selected' : ''}`}
      onClick={onSelect}
      aria-pressed={selected}
    >
      {recommended && (
        <span className="route-card__badge">
          <Icon name="sparkle" size={13} /> Recommended
        </span>
      )}
      <span className="route-card__label">
        {kind === 'baseline' ? 'Shortest' : 'WalkLah route'}
        <Icon name="walk" size={18} />
      </span>
      <span className="route-card__minutes">{formatMinutes(route.estimated_minutes)}</span>
      <span className="route-card__meta">
        {formatMetres(route.distance_m)}
        {kind === 'baseline' ? ' · usual path' : ''}
      </span>
      {baseline && Math.round(extraMetres) !== 0 && (
        <span className="route-card__delta">
          {formatSigned(extraMetres, 'm')} · {formatSigned(extraMinutes, 'min', 1)}
        </span>
      )}
      <span className="route-card__select">{selected ? 'Shown on map' : 'Show on map'}</span>
    </button>
  )
}

function DistanceBar({ label, metres, longest, tone }: { label: string; metres: number; longest: number; tone: 'grey' | 'green' }) {
  const width = longest > 0 ? Math.max(4, (metres / longest) * 100) : 0
  return (
    <div className={`distance-bar distance-bar--${tone}`}>
      <span className="distance-bar__label">{label}</span>
      <span className="distance-bar__track">
        <span className="distance-bar__fill" style={{ width: `${width}%` }} />
      </span>
      <span className="distance-bar__value">{formatMetres(metres)}</span>
    </div>
  )
}

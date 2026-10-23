import { Icon, type IconName } from '../../components/icons'
import { categoryLabel } from '../../config/categories'
import { SEGMENT_COLORS } from '../../map/routeLayers'
import type { PlannedRoute, RainMode, RouteMode, RouteOption, RoutesResponse } from '../../types'
import { formatMetres, formatMinutes, formatSigned } from '../../utils/format'
import type { RoutesState } from '../GoApp'
import { t } from '../i18n'
import { hourFor, TIME_CHOICES, timeLabel, type GoPrefs, type TimeChoice } from '../lib'
import { reasonText } from '../reasons'
import { TripCard } from '../TripCard'
import type { Endpoint } from '../types'
import { uvLabel, type HourWeather } from '../useWeather'

const MODE_INFO: Record<RouteMode, { title: string; icon: IconName; hint: string }> = {
  shortest: { title: 'Shortest', icon: 'walk', hint: 'Distance only' },
  practical: { title: 'Practical', icon: 'shield', hint: 'Fewer barriers' },
  enjoyable: { title: 'Enjoyable', icon: 'leaf', hint: 'Shade & quiet' },
}

const RAIN_NEXT: Record<RainMode, RainMode> = { auto: 'on', on: 'off', off: 'auto' }

interface Props {
  from: Endpoint | null
  to: Endpoint | null
  onOpenPicker: (which: 'from' | 'to') => void
  onSwap: () => void
  timeChoice: TimeChoice
  onTime: (t: TimeChoice) => void
  prefs: GoPrefs
  onPrefs: (p: GoPrefs) => void
  routes: RoutesState
  selected: RouteMode
  recommended: RouteMode
  onSelect: (mode: RouteMode) => void
  weather: HourWeather[] | null
  onFeedback: () => void
  onStartWalk: (preview: boolean) => void
}

export function ExploreScreen(props: Props) {
  const { from, to, onOpenPicker, onSwap, timeChoice, onTime, prefs, onPrefs, routes } = props
  const data = routes.status === 'ready' ? routes.data : null
  const rainLabel =
    prefs.rain === 'auto'
      ? data?.weather.rain_probability != null
        ? t('Rain: auto ({p}%)', { p: Math.round(data.weather.rain_probability) })
        : t('Rain: auto')
      : prefs.rain === 'on'
        ? t('Rain cover: on')
        : t('Rain cover: off')
  return (
    <div className="explore">
      <TripCard compact from={from} to={to} onOpenPicker={onOpenPicker} onSwap={onSwap} />

      <div className="chip-row" role="radiogroup" aria-label={t('Leave at')}>
        {TIME_CHOICES.map((choice) => (
          <button
            key={choice}
            type="button"
            role="radio"
            aria-checked={choice === timeChoice}
            className={`chip${choice === timeChoice ? ' is-active' : ''}`}
            onClick={() => onTime(choice)}
          >
            {choice === 'now' ? <Icon name="clock" size={14} /> : null}
            {timeLabel(choice)}
          </button>
        ))}
      </div>
      <div className="chip-row">
        <button
          type="button"
          role="switch"
          aria-checked={prefs.stepFree}
          className={`chip${prefs.stepFree ? ' is-active' : ''}`}
          onClick={() => onPrefs({ ...prefs, stepFree: !prefs.stepFree })}
        >
          <Icon name="wheelchair" size={14} /> {t('Step-free')}
        </button>
        <button
          type="button"
          className={`chip${data?.weather.rain_cover ? ' is-active is-rain' : ''}`}
          onClick={() => onPrefs({ ...prefs, rain: RAIN_NEXT[prefs.rain] })}
          title={t('Auto turns rain cover on when rain is 60% likely or more')}
        >
          <Icon name="umbrella" size={14} /> {rainLabel}
        </button>
      </div>

      <Conditions data={data} weather={props.weather} hour={hourFor(timeChoice)} />

      <Results {...props} />
    </div>
  )
}

function Conditions({ data, weather, hour }: { data: RoutesResponse | null; weather: HourWeather[] | null; hour: number }) {
  const w = weather?.[hour]
  if (!data) return null
  const sun = data.sun
  return (
    <div className={`conditions${sun.daylight ? '' : ' is-night'}`}>
      <span className="conditions__sun">
        <Icon name={sun.daylight ? 'sun' : 'moon'} size={16} />
        {sun.daylight
          ? sun.altitude > 60
            ? t('Sun high ({deg}°): short shadows', { deg: Math.round(sun.altitude) })
            : t('Sun low in the {dir}: long shadows', { dir: t(compass(sun.azimuth)) })
          : t('After dark: lighting over shade')}
      </span>
      {w && (
        <span className="conditions__weather">
          {Math.round(w.temperature)}°C · UV {Math.round(w.uv)} {t(uvLabel(w.uv))} · {t('rain')} {w.rain}%
        </span>
      )}
    </div>
  )
}

function compass(azimuth: number): string {
  return ['north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west'][
    Math.round(azimuth / 45) % 8
  ]
}

function Results({ from, to, routes, selected, recommended, onSelect, onFeedback, onStartWalk }: Props) {
  if (!from || !to) return <p className="empty-note">{t('Choose a start and a destination to compare routes.')}</p>
  if (routes.status === 'idle') return <p className="empty-note">{t('Routes appear once WalkLah is reachable.')}</p>
  if (routes.status === 'loading') {
    return (
      <div className="loading-card" role="status">
        <span className="spinner" aria-hidden="true" />
        <div>
          <strong>{t('Comparing routes…')}</strong>
          <span>{t('Working out shade along every path for that time.')}</span>
        </div>
      </div>
    )
  }
  if (routes.status === 'error') {
    return (
      <p className="inline-error" role="alert">
        {routes.message}
      </p>
    )
  }
  const data = routes.data
  const shortest = data.routes.find((r): r is PlannedRoute => r.mode === 'shortest' && r.available)!
  const chosen = data.routes.find((r): r is PlannedRoute => r.mode === selected && r.available) ?? shortest
  const night = !data.sun.daylight
  const audited = data.start.in_pilot_area && data.end.in_pilot_area
  return (
    <section className="results" aria-label={t('Route options')}>
      <div className="mode-cards">
        {data.routes.map((route) => (
          <ModeCard
            key={route.mode}
            route={route}
            shortest={shortest}
            night={night}
            selected={route.mode === chosen.mode}
            recommended={route.mode === recommended}
            onSelect={() => onSelect(route.mode)}
          />
        ))}
      </div>

      <div className="start-row">
        <button type="button" className="btn btn--primary btn--large start-row__go" onClick={() => onStartWalk(false)}>
          <Icon name="navigation" size={20} className="accent-icon" /> {t('Start walking')}
        </button>
        <button type="button" className="btn btn--large start-row__preview" onClick={() => onStartWalk(true)}>
          <Icon name="play" size={18} /> {t('Preview')}
        </button>
      </div>

      <RouteDetail route={chosen} night={night} />

      <Legend night={night} />

      <p className="fine-print">
        {t('Comfort estimates from OpenStreetMap, tree-canopy and sun data — not a safety guarantee.')}{' '}
        {!audited && t('Conditions here come from map data; our on-foot audit covers the UM area so far.')}{' '}
        {data.data_notes.estimated_building_height_pct >= 50 &&
          t('{pct}% of building heights are estimated.', { pct: Math.round(data.data_notes.estimated_building_height_pct) })}{' '}
        {t('Tap a coloured path for its details.')}
      </p>
      <button type="button" className="btn btn--block" onClick={onFeedback}>
        <Icon name="thumbUp" size={18} /> {t('After your walk: was it passable?')}
      </button>
    </section>
  )
}

function ModeCard({
  route,
  shortest,
  night,
  selected,
  recommended,
  onSelect,
}: {
  route: RouteOption
  shortest: PlannedRoute
  night: boolean
  selected: boolean
  recommended: boolean
  onSelect: () => void
}) {
  const info = MODE_INFO[route.mode]
  if (!route.available) {
    return (
      <div className="mode-card mode-card--missing" role="alert">
        <span className="mode-card__title">
          <Icon name={info.icon} size={16} /> {t(info.title)}
        </span>
        <p>{t(route.reason)}</p>
      </div>
    )
  }
  const extra = route.distance_m - shortest.distance_m
  const metric = night
    ? t('{pct}% known lit', { pct: Math.round((route.lighting.lit_m / Math.max(route.distance_m, 1)) * 100) })
    : route.exposure
      ? t('{pct}% shade', { pct: Math.round(route.exposure.shade_pct) })
      : ''
  return (
    <button
      type="button"
      className={`mode-card mode-card--${route.mode}${selected ? ' is-selected' : ''}`}
      aria-pressed={selected}
      onClick={onSelect}
    >
      {recommended && <span className="mode-card__badge">{t('For you')}</span>}
      <span className="mode-card__title">
        <Icon name={info.icon} size={16} /> {t(info.title)}
      </span>
      <span className="mode-card__minutes">{formatMinutes(route.estimated_minutes)}</span>
      <span className="mode-card__meta">
        {formatMetres(route.distance_m)}
        {route.mode !== 'shortest' && Math.round(extra) !== 0 ? ` · ${formatSigned(extra, 'm')}` : ''}
      </span>
      {metric && (
        <span className="mode-card__metric">
          <Icon name={night ? 'bulb' : 'tree'} size={13} /> {metric}
        </span>
      )}
      {route.warnings.length > 0 && (
        <span className="mode-card__warn">
          <Icon name="alert" size={13} /> {t('{n} unverified', { n: route.warnings.length })}
        </span>
      )}
    </button>
  )
}

function RouteDetail({ route, night }: { route: PlannedRoute; night: boolean }) {
  return (
    <div className="route-detail">
      <h3>
        {t('Why this {mode} route', { mode: t(MODE_INFO[route.mode].title).toLowerCase() })}
        {route.long_detour && (
          <span className="status-badge status-badge--amber status-badge--small">{t('Long detour')}</span>
        )}
      </h3>
      <ul className="reason-list">
        {route.reasons.map((reason) => (
          <li key={reason}>{reasonText(reason)}</li>
        ))}
      </ul>
      {!night && route.exposure && (
        <div className="exposure-bar" aria-label={t('{pct}% of the route in shade', { pct: Math.round(route.exposure.shade_pct) })}>
          <span className="exposure-bar__shade" style={{ width: `${route.exposure.shade_pct}%` }} />
        </div>
      )}
      {night && (
        <div className="exposure-bar exposure-bar--night">
          <span style={{ width: `${(route.lighting.lit_m / Math.max(route.distance_m, 1)) * 100}%`, background: SEGMENT_COLORS.lit }} />
          <span style={{ width: `${(route.lighting.unlit_m / Math.max(route.distance_m, 1)) * 100}%`, background: SEGMENT_COLORS.unlit }} />
        </div>
      )}
      {route.warnings.length > 0 && (
        <div className="warning-box">
          <Icon name="alert" size={16} />
          <span>
            {t("{what} reported on this route — not yet verified or confirmed by enough walkers, so WalkLah doesn't reroute around it.", {
              what: route.warnings.map((w) => t(categoryLabel(w.category))).join(', '),
            })}
          </span>
        </div>
      )}
    </div>
  )
}

function Legend({ night }: { night: boolean }) {
  const items: [string, string][] = night
    ? [
        [SEGMENT_COLORS.lit, 'Lit'],
        [SEGMENT_COLORS.unlit, 'Not lit'],
        [SEGMENT_COLORS.unknown, 'Lighting unknown'],
      ]
    : [
        [SEGMENT_COLORS.shade, 'Shade'],
        [SEGMENT_COLORS.sun, 'Sun'],
        [SEGMENT_COLORS.unknown, 'Unknown'],
      ]
  return (
    <div className="route-legend" aria-label={t('Map colours')}>
      {items.map(([color, label]) => (
        <span key={label}>
          <i style={{ background: color }} /> {t(label)}
        </span>
      ))}
      <span>
        <i className="route-legend__dots" /> {t('Shortest')}
      </span>
    </div>
  )
}

import type { SVGProps } from 'react'

// Small outline icon set drawn for WalkLah (24×24, 2px stroke, currentColor).
// Kept inline so the app needs no icon package.

const paths = {
  sun: 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
  moon: 'M20 14.5A8 8 0 1 1 9.5 4 6.5 6.5 0 0 0 20 14.5z',
  bulb: 'M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z',
  train: 'M7 3h10a2 2 0 0 1 2 2v9a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V5a2 2 0 0 1 2-2zM5 10h14M9 14h.01M15 14h.01M8 21l2-4M16 21l-2-4',
  bus: 'M5 4h14v12H5zM5 11h14M8 19v-3M16 19v-3M8 14h.01M16 14h.01',
  tree: 'M12 22v-6M12 2l6 8h-3l4 6H5l4-6H6l6-8z',
  wheelchair: 'M11 4.5a1.5 1.5 0 1 0 0-.01M10 8l1 6h5l2 5M9 10a5 5 0 1 0 6 7',
  book: 'M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2V5zM4 19a2 2 0 0 1 2-2h12',
  coffee: 'M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9zM16 10h2a2 2 0 0 1 0 4h-2M8 3v3M12 3v3',
  leaf: 'M5 19c0-8 6-14 15-14 0 9-6 15-14 15M5 19l8-8',
  heart: 'M12 20s-8-4.5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 9c0 6.5-8 11-8 11z',
  upload: 'M12 16V4M7 9l5-5 5 5M4 20h16',
  download: 'M12 4v12M7 11l5 5 5-5M4 20h16',
  lock: 'M6 11h12v9H6zM8 11V8a4 4 0 0 1 8 0v3',
  plus: 'M12 5v14M5 12h14',
  thumbUp: 'M7 11v9H4v-9h3zM7 11l4-7a2 2 0 0 1 3 2l-1 4h5a2 2 0 0 1 2 2l-1.5 6a2 2 0 0 1-2 1.5H7',
  arrowUp: 'M12 19V5M6 11l6-6 6 6',
  home: 'M4 11l8-7 8 7M6 10v10h4v-6h4v6h4V10',
  route: 'M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM8 17h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7',
  flag: 'M5 21V4M5 4h11l-2 4 2 4H5',
  users: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20v-1a5 5 0 0 1 10 0v1M16 11a3 3 0 1 0 0-6M21 20v-1a5 5 0 0 0-4-4.9',
  chart: 'M4 20h16M7 16v-4M12 16V8M17 16v-7',
  walk: 'M13.6 3.3a1 1 0 1 0 0 2a1 1 0 1 0 0-2M12.6 8l-1.8 6.2M10.8 14.2l2.6 3l.5 3.8M10.8 14.2l-1.5 3.6l-2.5 2.8M12.2 9.4l2.8 2.4l2.6.6M12.2 9.4l-2.8 1.5l-1.6 2.7',
  swap: 'M8 4v16M8 4L5 7M8 4l3 3M16 20V4M16 20l-3-3M16 20l3-3',
  x: 'M6 6l12 12M18 6L6 18',
  pin: 'M12 21s-6-5.6-6-11a6 6 0 0 1 12 0c0 5.4-6 11-6 11zM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',
  layers: 'M12 4l8 4-8 4-8-4 8-4zM4 12l8 4 8-4M4 16l8 4 8-4',
  locate: 'M12 19a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM12 2v3M12 19v3M2 12h3M19 12h3',
  chevronRight: 'M9 6l6 6-6 6',
  chevronLeft: 'M15 6l-6 6 6 6',
  arrowRight: 'M5 12h14M13 6l6 6-6 6',
  check: 'M5 12l5 5 9-10',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  alert: 'M12 4L2.5 20h19L12 4zM12 10v4M12 17v.01',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5M12 8v.01',
  refresh: 'M20 11a8 8 0 0 0-14.6-4.5M4 4v4h4M4 13a8 8 0 0 0 14.6 4.5M20 20v-4h-4',
  shoe: 'M4 15h16v2a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-2zM4 15V7l4 1 2 3 4 1 4 1a2 2 0 0 1 2 2',
  barrier: 'M3 8h18v6H3zM6 14v5M18 14v5M7 8l-3 6M13 8l-3 6M19 8l-3 6',
  flood: 'M3 8c2-2 4-2 6 0s4 2 6 0 4-2 6 0M3 13c2-2 4-2 6 0s4 2 6 0 4-2 6 0M3 18c2-2 4-2 6 0s4 2 6 0 4-2 6 0',
  crane: 'M6 21V5M6 5h14M6 5l4-2M17 5v5M15 13h4l-2-3M3 21h8',
  road: 'M5 20L9 4M19 20L15 4M12 6v2M12 11v2M12 16v2',
  crossing: 'M12 5a1.5 1.5 0 1 0 0-.01M9 21l1.5-5 2.5 2v3M8 11l1.5-3h4l2 3M3 21h3M18 21h3',
  dots: 'M5 12h.01M12 12h.01M19 12h.01',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4',
  map: 'M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2V6zM9 4v14M15 6v14',
  shield: 'M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3zM9 12l2 2 4-4',
  message: 'M4 5h16v11H9l-5 4V5z',
  target: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01',
  sparkle: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z',
  bag: 'M5 8h14l-1 12H6L5 8zM9 8V6a3 3 0 0 1 6 0v2',
  food: 'M7 3v8M5 3v5a2 2 0 0 0 4 0V3M7 11v10M17 21V3c-2 1-3 3-3 6v4h3',
  turnLeft: 'M9 5L4 10l5 5M4 10h9a5 5 0 0 1 5 5v5',
  turnRight: 'M15 5l5 5-5 5M20 10h-9a5 5 0 0 0-5 5v5',
  slightLeft: 'M7 4v6h6M7 10l8 8v3',
  slightRight: 'M17 4v6h-6M17 10l-8 8v3',
  straight: 'M12 20V4M7 9l5-5 5 5',
  navigation: 'M12 2l7 19-7-4-7 4 7-19z',
  play: 'M7 4l13 8-13 8V4z',
  pause: 'M7 4h3v16H7zM14 4h3v16h-3z',
  umbrella: 'M3 12a9 9 0 0 1 18 0H3zM12 12v7a2 2 0 0 1-4 0M12 3v0',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z',
  stairs: 'M3 20h5v-5h5v-5h5V5h3',
  flagEnd: 'M5 21V4M5 4h14v8H5M9 4v8M13 4v8M17 4v8',
  camera: 'M4 8h3l2-3h6l2 3h3v11H4V8zM12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z',
  image: 'M4 5h16v14H4V5zM4 16l5-5 4 4 3-3 4 4M15 9.5a1.5 1.5 0 1 0 0-.01',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 0 0-2-1.2L14.2 3h-4l-.4 2.6a7 7 0 0 0-2 1.2l-2.3-.9-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-.9a7 7 0 0 0 2 1.2l.4 2.6h4l.4-2.6a7 7 0 0 0 2-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z',
} as const

export type IconName = keyof typeof paths

interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'name'> {
  name: IconName
  size?: number
  label?: string
}

export function Icon({ name, size = 20, label, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
      {...rest}
    >
      <path d={paths[name]} />
    </svg>
  )
}

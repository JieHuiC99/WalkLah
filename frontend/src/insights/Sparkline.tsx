/** Weekly counts as a small bar sparkline (inline SVG, no chart library). */
export function Sparkline({
  label,
  values,
  weeks,
  color = 'var(--green)',
}: {
  label: string
  values: number[]
  weeks: string[]
  color?: string
}) {
  const max = Math.max(1, ...values)
  const w = 8
  const gap = 4
  const h = 36
  const total = values.reduce((a, b) => a + b, 0)
  const last = values[values.length - 1] ?? 0
  return (
    <figure className="sparkline">
      <figcaption>
        <span>{label}</span>
        <strong>{last}</strong>
        <small>this week · {total} in 8 weeks</small>
      </figcaption>
      <svg
        width={values.length * (w + gap)}
        height={h}
        role="img"
        aria-label={`${label}: ${values.map((v, i) => `week of ${weeks[i]}: ${v}`).join(', ')}`}
      >
        {values.map((v, i) => {
          const bh = Math.max(2, (v / max) * (h - 2))
          return (
            <rect
              key={weeks[i] ?? i}
              x={i * (w + gap)}
              y={h - bh}
              width={w}
              height={bh}
              rx={2}
              fill={i === values.length - 1 ? color : 'var(--line)'}
            >
              <title>
                {weeks[i]}: {v}
              </title>
            </rect>
          )
        })}
      </svg>
    </figure>
  )
}

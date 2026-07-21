import { motion, useReducedMotion } from 'framer-motion'
import { REDUCED_TWEEN, SPRING, type Layer } from '../design/tokens'

interface Opt<T extends string> {
  value: T
  label: string
}

export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: Opt<T>[]
  value: T
  onChange: (v: T) => void
}) {
  const reduce = useReducedMotion()
  return (
    <div className="flex shrink-0 items-center gap-2">
      <span className="micro hidden whitespace-nowrap text-ink3 lg:block">{label}</span>
      <div
        role="group"
        aria-label={label}
        className="inline-flex h-9 items-center gap-0.5 rounded-full border border-line bg-surface/60 p-1"
      >
        {options.map((o) => {
          const active = o.value === value
          return (
            <button
              key={o.value}
              aria-pressed={active}
              onClick={() => onChange(o.value)}
              className={`relative h-7 whitespace-nowrap rounded-full px-3 text-[13px] font-medium transition-colors ${
                active ? 'text-page' : 'text-ink2 hover:text-ink'
              }`}
            >
              {active && (
                <motion.span
                  layoutId={`seg-pill-${label}`}
                  className="absolute inset-0 rounded-full bg-ink"
                  transition={reduce ? REDUCED_TWEEN : SPRING}
                />
              )}
              <span className="relative z-10">{o.label}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

export default function LayerToggle({
  layer,
  onChange,
}: {
  layer: Layer
  onChange: (l: Layer) => void
}) {
  return (
    <Segmented<Layer>
      label="Color by"
      value={layer}
      onChange={onChange}
      options={[
        { value: 'exposure', label: 'AI exposure' },
        { value: 'pay', label: 'Median pay' },
      ]}
    />
  )
}

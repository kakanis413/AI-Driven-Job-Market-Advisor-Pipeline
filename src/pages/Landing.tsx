import { useMemo } from 'react'
import {
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
  type MotionValue,
} from 'framer-motion'
import { exposureColor, fmtExposure } from '../design/scales'
import { EXPOSURE_STOPS, FAMILY_ORDER, type Mode } from '../design/tokens'
import { useMeasure } from '../hooks/useMeasure'
import { layoutTreemap } from '../lib/layout'
import type { Major } from '../types'

const EASE = [0.22, 1, 0.36, 1] as const
const HEADLINE = ['How', 'exposed', 'is', 'your', 'major', 'to', 'AI?']

interface Props {
  majors: Major[]
  mode: Mode
  onExplore: (sub?: 'heatmap') => void
}

export default function Landing({ majors, mode, onExplore }: Props) {
  const reduce = useReducedMotion()
  const expC = useMemo(() => exposureColor(mode), [mode])
  const data = useMemo(() => (majors.length ? majors : placeholder()), [majors])
  const familyCount = useMemo(
    () => new Set(data.map((m) => m.family)).size,
    [data],
  )

  // Pointer parallax: the ambient map drifts a few px against the cursor.
  const mx = useMotionValue(0)
  const my = useMotionValue(0)
  const px = useSpring(useTransform(mx, (v) => v * -0.016), { stiffness: 50, damping: 18 })
  const py = useSpring(useTransform(my, (v) => v * -0.016), { stiffness: 50, damping: 18 })

  return (
    <section
      onPointerMove={(e) => {
        mx.set(e.clientX - window.innerWidth / 2)
        my.set(e.clientY - window.innerHeight / 2)
      }}
      className="relative flex min-h-[calc(100dvh-170px)] flex-col overflow-hidden"
    >
      <AmbientMap data={data} mode={mode} px={px} py={py} reduce={!!reduce} />

      <div className="relative mx-auto flex w-full max-w-[1400px] flex-1 flex-col justify-center px-5 py-14 md:px-8">
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.05, ease: EASE }}
          className="micro flex items-center gap-2.5 text-ink3"
        >
          <span aria-hidden className="flex gap-1">
            {[0, 1, 3, 4].map((i) => (
              <span
                key={i}
                className="size-1.5 rounded-full"
                style={{ background: EXPOSURE_STOPS[mode][i] }}
              />
            ))}
          </span>
          An interactive field guide to AI &amp; your degree
        </motion.p>

        <h1
          aria-label="How exposed is your major to AI?"
          className="mt-5 max-w-5xl text-[clamp(2.6rem,7.2vw,6.2rem)] leading-[1.02] tracking-[-0.035em] text-ink [font-weight:660]"
        >
          {HEADLINE.map((word, i) => (
            <span
              key={i}
              aria-hidden
              className="-mb-[0.14em] inline-block overflow-hidden pb-[0.14em] align-bottom"
            >
              <motion.span
                className="mr-[0.24em] inline-block"
                initial={reduce ? { opacity: 0 } : { y: '108%' }}
                animate={reduce ? { opacity: 1 } : { y: 0 }}
                transition={{ duration: 0.75, delay: 0.12 + i * 0.055, ease: EASE }}
              >
                {word === 'exposed' ? (
                  <span
                    style={{
                      backgroundImage: `linear-gradient(90deg, ${EXPOSURE_STOPS[mode].join(', ')})`,
                      WebkitBackgroundClip: 'text',
                      backgroundClip: 'text',
                      color: 'transparent',
                    }}
                  >
                    {word}
                  </span>
                ) : (
                  word
                )}
              </motion.span>
            </span>
          ))}
        </h1>

        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.5, ease: EASE }}
          className="mt-6 max-w-xl text-[16px] leading-relaxed text-ink2"
        >
          Every field of study, sized by graduates and colored by how much of the work AI can
          already reach — with an advisor to talk it through. Grounded in public data; task
          exposure scored 0–10.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.62, ease: EASE }}
          className="mt-9 flex flex-wrap items-center gap-4"
        >
          <motion.button
            onClick={() => onExplore()}
            whileHover={reduce ? undefined : { scale: 1.02 }}
            whileTap={reduce ? undefined : { scale: 0.98 }}
            className="group flex h-13 items-center gap-3 rounded-full bg-ink py-3 pl-6 pr-4 text-[15px] font-semibold text-page shadow-lg shadow-black/10"
          >
            Explore the map
            <span
              aria-hidden
              className="grid size-7 place-items-center rounded-full bg-page/20 transition-transform duration-200 group-hover:translate-x-0.5"
            >
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                <path
                  d="M1.5 6.5h10m0 0L7 2m4.5 4.5L7 11"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
          </motion.button>
          <button
            onClick={() => onExplore('heatmap')}
            className="h-11 rounded-full border border-line bg-surface/70 px-5 text-[14px] font-medium text-ink2 backdrop-blur transition-colors hover:border-ink3 hover:text-ink"
          >
            Straight to the heatmap
          </button>
        </motion.div>

        <motion.dl
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.85 }}
          className="mt-12 flex flex-wrap gap-x-10 gap-y-4"
        >
          <Stat value={majors.length ? String(majors.length) : '—'} label="majors mapped" />
          <Stat value={String(familyCount)} label="fields of study" />
          <Stat value="0–10" label="task-level exposure" />
          <Stat value="Live" label="career advisor" />
        </motion.dl>
      </div>

      {majors.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 1.05 }}
          aria-hidden
          className="relative border-t border-line py-3.5"
        >
          <div className="marquee gap-9 pr-9">
            {[...majors, ...majors].map((m, i) => (
              <span key={i} className="flex shrink-0 items-center gap-2 text-[13px] text-ink2">
                <span className="size-2 rounded-full" style={{ background: expC(m.exposure) }} />
                {m.major}
                <b
                  className="font-semibold text-ink"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {fmtExposure(m.exposure)}
                </b>
              </span>
            ))}
          </div>
        </motion.div>
      )}
    </section>
  )
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div>
      <dd className="text-[16px] font-semibold text-ink" style={{ fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </dd>
      <dt className="micro mt-0.5 text-ink3">{label}</dt>
    </div>
  )
}

/** Full-bleed, dimmed live treemap of the real data — the hero visual IS the
 *  encoding the app teaches. Oversized so parallax never reveals an edge. */
function AmbientMap({
  data,
  mode,
  px,
  py,
  reduce,
}: {
  data: Major[]
  mode: Mode
  px: MotionValue<number>
  py: MotionValue<number>
  reduce: boolean
}) {
  const { ref, width, height } = useMeasure<HTMLDivElement>()
  const expC = useMemo(() => exposureColor(mode), [mode])
  const PAD = 70
  const tiles = useMemo(
    () => (width > 0 ? layoutTreemap(data, width + PAD * 2, height + PAD * 2).tiles : []),
    [data, width, height],
  )
  return (
    <div ref={ref} aria-hidden className="absolute inset-0">
      <motion.svg
        width={width + PAD * 2}
        height={height + PAD * 2}
        style={{ x: px, y: py, position: 'absolute', left: -PAD, top: -PAD }}
      >
        {tiles.map((t, i) => (
          <motion.rect
            key={t.major.cip}
            x={t.x}
            y={t.y}
            width={t.w}
            height={t.h}
            rx={5}
            fill={expC(t.major.exposure)}
            stroke="var(--page)"
            strokeWidth={2}
            initial={{ opacity: 0 }}
            animate={{ opacity: mode === 'light' ? 0.3 : 0.34 }}
            transition={{ duration: 0.9, delay: reduce ? 0 : Math.min(i * 0.035, 1.1) }}
          />
        ))}
      </motion.svg>
      <div
        className="absolute inset-0"
        style={{
          background:
            'linear-gradient(90deg, var(--page) 14%, color-mix(in srgb, var(--page) 55%, transparent) 52%, color-mix(in srgb, var(--page) 18%, transparent) 100%)',
        }}
      />
      <div
        className="absolute inset-x-0 bottom-0 h-44"
        style={{ background: 'linear-gradient(180deg, transparent, var(--page) 85%)' }}
      />
    </div>
  )
}

/** Placeholder mosaic while data loads, so the hero never renders empty. */
function placeholder(): Major[] {
  const weights = [34, 21, 18, 14, 12, 10, 9, 8, 7, 6, 5, 5, 4, 4, 3, 3]
  return weights.map((completions, i) => ({
    cip: `ph-${i}`,
    major: '',
    family: FAMILY_ORDER[i % FAMILY_ORDER.length],
    completions,
    exposure: (i * 3.7) % 10,
    median_pay: 0,
    growth: 'average',
    occupations: [],
    rationale: '',
  }))
}

import { useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { exposureColor, fmtExposure, normalize } from '../design/scales'
import { EXPOSURE_STOPS, FAMILY_ORDER, type Mode } from '../design/tokens'
import { useMeasure } from '../hooks/useMeasure'
import { demoExposure } from '../lib/heroDemo'
import { layoutTreemap } from '../lib/layout'
import type { Major } from '../types'

const EASE = [0.22, 1, 0.36, 1] as const

/** Statement, not a question — it pairs with the search field as an invitation.
 *  "Integrating into" describes a process, not a vulnerability. */
const HEADLINE = 'See how AI is integrating into your major.'
const ACCENT_WORD = 'integrating'

interface Props {
  majors: Major[]
  mode: Mode
  /** Search submit / Enter: hand off to Explore, seeding its search. */
  onExplore: (query?: string) => void
  /** Click a tile: hand off to Explore with that major selected. */
  onSelectMajor: (cip: string) => void
  /** The advisor chip: open the chat in Explore. */
  onOpenAdvisor: () => void
}

interface Hover {
  major: Major
  demo: number
  x: number
  y: number
}

export default function Landing({ majors, mode, onExplore, onSelectMajor, onOpenAdvisor }: Props) {
  const reduce = useReducedMotion()
  const data = useMemo(() => (majors.length ? majors : placeholder()), [majors])
  const [heroQuery, setHeroQuery] = useState('')
  const [hover, setHover] = useState<Hover | null>(null)

  return (
    <section className="relative flex min-h-[calc(100dvh-118px)] flex-col overflow-hidden">
      {/* The hero IS the product: a full-bleed, full-color, interactive treemap.
          Colored by demo exposure so the ramp shows range while the pipeline is
          flat (heroDemo.ts). Hover reveals a name; click opens it in Explore. */}
      <HeroMap
        data={data}
        mode={mode}
        reduce={!!reduce}
        query={heroQuery}
        onHover={setHover}
        onPick={(m) => onSelectMajor(m.cip)}
      />

      {hover && <HoverLabel hover={hover} mode={mode} />}

      {/* Copy floats over the map in glass — content behind it to refract. The
          wrapper is click-through; only the panel itself captures pointer. */}
      <div className="pointer-events-none relative z-10 mx-auto flex w-full max-w-[1400px] flex-1 items-center px-5 md:px-8">
        <motion.div
          initial={reduce ? { opacity: 0 } : { opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reduce ? { duration: 0.15 } : { duration: 0.6, delay: 0.55, ease: EASE }}
          className="glass pointer-events-auto w-full max-w-lg rounded-panel p-6 shadow-2xl shadow-black/10 md:p-8"
        >
          <p className="micro flex items-center gap-2.5 text-ink3">
            <span aria-hidden className="flex gap-1">
              {[0, 1, 3, 4].map((i) => (
                <span key={i} className="size-1.5 rounded-full" style={{ background: EXPOSURE_STOPS[mode][i] }} />
              ))}
            </span>
            An interactive field guide to AI and what you study
          </p>

          <h1 className="mt-4 text-[clamp(2.1rem,4.4vw,3.4rem)] font-[660] leading-[1.05] tracking-[-0.03em] text-ink">
            {HEADLINE.split(' ').map((word, i) => {
              const clean = word.replace(/[^a-z]/gi, '')
              return (
                <span key={i} className="mr-[0.24em] inline-block">
                  {clean === ACCENT_WORD ? (
                    <span
                      className="font-display pr-[0.05em] font-[600]"
                      style={{
                        backgroundImage: `linear-gradient(92deg, ${EXPOSURE_STOPS[mode][1]}, ${EXPOSURE_STOPS[mode][3]})`,
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
                </span>
              )
            })}
          </h1>

          <p className="mt-4 max-w-md text-[15px] leading-relaxed text-ink2">
            Every field of study, sized by graduates and colored by how much of the work AI can
            already reach. Hover a tile for its major; open one to talk it through with the advisor.
          </p>
          <p className="mt-2.5 text-[13.5px] leading-relaxed text-ink3">
            High exposure means the mix of tasks is likely to change — not that the job goes away.
          </p>

          {/* Search stays (typing highlights the live map behind); CTAs gone. */}
          <form
            onSubmit={(e) => {
              e.preventDefault()
              onExplore(heroQuery.trim() || undefined)
            }}
            className="mt-6 flex h-12 items-center gap-2 rounded-full border border-line bg-raised/80 pl-4 pr-2 shadow-sm focus-within:border-accent"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden className="shrink-0 text-ink3">
              <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.6" />
              <path d="m14 14-3-3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
            <input
              value={heroQuery}
              onChange={(e) => setHeroQuery(e.target.value)}
              placeholder="Find your major…"
              aria-label="Find your major"
              className="h-full min-w-0 flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-ink3"
            />
            <motion.button
              type="submit"
              whileHover={reduce ? undefined : { scale: 1.05 }}
              whileTap={reduce ? undefined : { scale: 0.95 }}
              aria-label="Explore the map"
              className="grid size-9 shrink-0 place-items-center rounded-full bg-ink text-page"
            >
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden>
                <path
                  d="M1.5 6.5h10m0 0L7 2m4.5 4.5L7 11"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </motion.button>
          </form>
        </motion.div>
      </div>

      {/* Floating glass chip — the advisor, discoverable from the first screen. */}
      <motion.button
        onClick={onOpenAdvisor}
        initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={reduce ? { duration: 0.15 } : { duration: 0.5, delay: 0.9, ease: EASE }}
        whileHover={reduce ? undefined : { scale: 1.03 }}
        whileTap={reduce ? undefined : { scale: 0.97 }}
        className="glass fixed bottom-16 right-5 z-20 flex items-center gap-2 rounded-full py-2.5 pl-4 pr-3 text-[13.5px] font-semibold text-ink shadow-xl shadow-black/15"
      >
        <span
          aria-hidden
          className="grid size-6 place-items-center rounded-full bg-ink text-page"
        >
          <svg width="13" height="13" viewBox="0 0 22 22" fill="none">
            <path
              d="M11 3a7.5 7.5 0 0 1 7.5 7.5c0 4.14-3.36 7.5-7.5 7.5-1.02 0-2-.2-2.88-.58L4 19l1.02-3.7A7.5 7.5 0 1 1 11 3Z"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        Ask about any major
        <span aria-hidden className="text-ink3">
          →
        </span>
      </motion.button>
    </section>
  )
}

/** Full-bleed interactive treemap. Colored by demo exposure; typing in the hero
 *  search highlights matches. Aria-hidden: it's a visual/pointer enhancement,
 *  and the keyboard-accessible path to every major is the search field. */
function HeroMap({
  data,
  mode,
  reduce,
  query,
  onHover,
  onPick,
}: {
  data: Major[]
  mode: Mode
  reduce: boolean
  query: string
  onHover: (h: Hover | null) => void
  onPick: (m: Major) => void
}) {
  const { ref, width, height } = useMeasure<HTMLDivElement>()
  const expC = useMemo(() => exposureColor(mode), [mode])
  const tiles = useMemo(
    () => (width > 0 ? layoutTreemap(data, width, height).tiles : []),
    [data, width, height],
  )
  const q = normalize(query.trim())

  return (
    <div ref={ref} aria-hidden className="absolute inset-0 z-0">
      <svg width={width} height={height} className="block">
        {tiles.map((t, i) => {
          const demo = demoExposure(t.major)
          const on = !q || normalize(t.major.major).includes(q) || normalize(t.major.family).includes(q)
          return (
            <motion.rect
              key={t.major.cip}
              x={t.x}
              y={t.y}
              width={t.w}
              height={t.h}
              rx={4}
              fill={expC(demo)}
              stroke="var(--page)"
              strokeWidth={1.5}
              className="cursor-pointer"
              initial={{ opacity: 0 }}
              animate={{ opacity: q ? (on ? 1 : 0.14) : 1 }}
              transition={{
                duration: q ? 0.25 : 0.5,
                delay: q || reduce ? 0 : Math.min(i * 0.012, 0.4),
              }}
              onPointerMove={(e) => onHover({ major: t.major, demo, x: e.clientX, y: e.clientY })}
              onPointerLeave={() => onHover(null)}
              onClick={() => onPick(t.major)}
            />
          )
        })}
      </svg>
      {/* Bottom scrim so the map fades into the pinned footer, never a hard cut. */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-32"
        style={{ background: 'linear-gradient(180deg, transparent, color-mix(in srgb, var(--page) 70%, transparent))' }}
      />
    </div>
  )
}

/** A small glass chip that trails the cursor, naming the hovered major. */
function HoverLabel({ hover, mode }: { hover: Hover; mode: Mode }) {
  const expC = useMemo(() => exposureColor(mode), [mode])
  return (
    <div
      className="glass pointer-events-none fixed z-30 flex items-center gap-2 rounded-full py-1.5 pl-2.5 pr-3 text-[12.5px] shadow-lg"
      style={{ left: hover.x + 14, top: hover.y + 14, maxWidth: 320 }}
    >
      <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ background: expC(hover.demo) }} />
      <span className="truncate font-medium text-ink">{hover.major.major}</span>
      <span className="shrink-0 text-ink3" style={{ fontVariantNumeric: 'tabular-nums' }}>
        {fmtExposure(hover.demo)}
      </span>
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

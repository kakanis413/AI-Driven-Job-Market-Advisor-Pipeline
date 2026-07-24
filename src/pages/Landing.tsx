import { useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { exposureColor, fmtExposure, inkFor, normalize } from '../design/scales'
import { EXPOSURE_STOPS, FAMILY_ORDER, type Mode } from '../design/tokens'
import { useMeasure } from '../hooks/useMeasure'
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
  /** No/!match on submit: hand off to Explore, seeding its search. */
  onExplore: (query?: string) => void
  /** Pick a result tile (or Enter on the top match): open it in Explore. */
  onSelectMajor: (cip: string) => void
  /** The advisor chip: open the chat in Explore. */
  onOpenAdvisor: () => void
}

interface Hover {
  major: Major
  x: number
  y: number
}

/** Rank matches: exact → starts-with → contains → family match. Ties break by
 *  program size, so the biggest program is the one Enter picks. */
function rankMatches(majors: Major[], query: string): Major[] {
  const q = normalize(query.trim())
  if (!q) return []
  const scored: { m: Major; rank: number }[] = []
  for (const m of majors) {
    const name = normalize(m.major)
    const family = normalize(m.family)
    const rank =
      name === q ? 0 : name.startsWith(q) ? 1 : name.includes(q) ? 2 : family.includes(q) ? 3 : -1
    if (rank >= 0) scored.push({ m, rank })
  }
  scored.sort((a, b) => a.rank - b.rank || (b.m.completions ?? 0) - (a.m.completions ?? 0))
  return scored.map((s) => s.m)
}

export default function Landing({ majors, mode, onExplore, onSelectMajor, onOpenAdvisor }: Props) {
  const reduce = useReducedMotion()
  const data = useMemo(() => (majors.length ? majors : placeholder()), [majors])
  const [heroQuery, setHeroQuery] = useState('')
  const [hover, setHover] = useState<Hover | null>(null)

  const q = heroQuery.trim()
  const matches = useMemo(() => rankMatches(data, q), [data, q])
  // Three states: no query → the whole map, small; matches → just those;
  // a query with nothing behind it → an honest message, never a blank box.
  const noMatches = q.length > 0 && matches.length === 0
  const results = q ? matches : data

  return (
    <section className="relative flex min-h-[calc(100dvh-118px)] flex-col overflow-hidden">
      <TextureMap data={data} mode={mode} />

      {hover && <HoverLabel hover={hover} mode={mode} />}

      <div className="relative z-10 mx-auto grid w-full max-w-[1400px] flex-1 items-center gap-8 px-5 py-10 md:px-8 lg:grid-cols-2 lg:gap-12">
        {/* Copy + search. Deliberately not glass: blur behind body text is a
            legibility tax (UI_REDESIGN §4) — glass is for the results frame. */}
        <div className="min-w-0">
          <motion.p
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={reduce ? { duration: 0.15 } : { duration: 0.5, delay: 0.1, ease: EASE }}
            className="micro flex items-center gap-2.5 text-ink3"
          >
            <span aria-hidden className="flex gap-1">
              {[0, 1, 3, 4].map((i) => (
                <span key={i} className="size-1.5 rounded-full" style={{ background: EXPOSURE_STOPS[mode][i] }} />
              ))}
            </span>
            An interactive field guide to AI and what you study
          </motion.p>

          <motion.h1
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={reduce ? { duration: 0.15 } : { duration: 0.6, delay: 0.18, ease: EASE }}
            className="mt-4 text-[clamp(2.1rem,4vw,3.3rem)] font-[660] leading-[1.05] tracking-[-0.03em] text-ink"
          >
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
          </motion.h1>

          <motion.div
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={reduce ? { duration: 0.15 } : { duration: 0.5, delay: 0.28, ease: EASE }}
          >
            <p className="mt-4 max-w-md text-[15px] leading-relaxed text-ink2">
              Every field of study, sized by bachelor's graduates and colored by how much of the work AI can
              already reach. Search to narrow the map, then open one to talk it through.
            </p>
            <p className="mt-2.5 text-[13.5px] leading-relaxed text-ink3">
              High exposure means the mix of tasks is likely to change — not that the job goes away.
            </p>

            <form
              onSubmit={(e) => {
                e.preventDefault()
                // Enter takes the top match; with nothing matching, the query
                // itself goes to Explore.
                if (matches.length > 0) onSelectMajor(matches[0].cip)
                else onExplore(q || undefined)
              }}
              className="mt-6 flex h-12 max-w-md items-center gap-2 rounded-full border border-line bg-raised/80 pl-4 pr-2 shadow-sm focus-within:border-accent"
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
                aria-label="Open the top match in Explore"
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

        {/* Live results panel. Glass on the FRAME only — the tiles inside stay
            fully opaque so the exposure encoding is never diluted. */}
        <motion.div
          initial={reduce ? { opacity: 0 } : { opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reduce ? { duration: 0.15 } : { duration: 0.6, delay: 0.34, ease: EASE }}
          className="glass flex h-[320px] min-w-0 flex-col rounded-panel p-3 shadow-2xl shadow-black/10 sm:h-[380px] lg:h-[470px]"
        >
          <div className="micro flex items-baseline justify-between gap-2 px-1 pb-2 text-ink3">
            <span>
              {q
                ? `${matches.length} ${matches.length === 1 ? 'match' : 'matches'}`
                : `All ${data.length} majors`}
            </span>
            <span className="truncate">
              {noMatches ? 'Try a different term' : q ? 'Click a tile to open it' : 'Type to narrow'}
            </span>
          </div>

          <div className="min-h-0 flex-1 overflow-hidden rounded-card">
            {noMatches ? (
              <div className="grid h-full place-items-center px-4 text-center">
                <p className="text-[13.5px] text-ink2">
                  No majors match “<span className="font-medium text-ink">{q}</span>”.
                </p>
              </div>
            ) : (
              <ResultsMap
                items={results}
                mode={mode}
                reduce={!!reduce}
                onHover={setHover}
                onPick={(m) => onSelectMajor(m.cip)}
              />
            )}
          </div>
        </motion.div>
      </div>

      {/* Floating glass chip — the advisor, discoverable from the first screen. */}
      <motion.button
        onClick={onOpenAdvisor}
        initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={reduce ? { duration: 0.15 } : { duration: 0.5, delay: 0.7, ease: EASE }}
        whileHover={reduce ? undefined : { scale: 1.03 }}
        whileTap={reduce ? undefined : { scale: 0.97 }}
        className="glass fixed bottom-16 right-5 z-20 flex items-center gap-2 rounded-full py-2.5 pl-4 pr-3 text-[13.5px] font-semibold text-ink shadow-xl shadow-black/15"
      >
        <span aria-hidden className="grid size-6 place-items-center rounded-full bg-ink text-page">
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

/** The results treemap: only the matching majors, rebuilt on each keystroke.
 *  Same `layoutTreemap` and violet exposure ramp as Explore, so the colour a
 *  major has here is the colour it has there. Tiles are solid — never glass. */
function ResultsMap({
  items,
  mode,
  reduce,
  onHover,
  onPick,
}: {
  items: Major[]
  mode: Mode
  reduce: boolean
  onHover: (h: Hover | null) => void
  onPick: (m: Major) => void
}) {
  const { ref, width, height } = useMeasure<HTMLDivElement>()
  const expC = useMemo(() => exposureColor(mode), [mode])
  const tiles = useMemo(
    () => (width > 8 && height > 8 ? layoutTreemap(items, width, height).tiles : []),
    [items, width, height],
  )
  const spring = reduce ? { duration: 0.15 } : { duration: 0.32, ease: EASE }

  return (
    <div ref={ref} className="size-full">
      <svg
        width={width}
        height={height}
        className="block"
        role="group"
        aria-label={`Treemap of ${items.length} majors, sized by bachelor's graduates and coloured by AI exposure`}
      >
        {tiles.map((t) => {
          const fill = expC(t.major.exposure)
          const ink = inkFor(fill)
          const showName = t.w > 76 && t.h > 34
          return (
            <motion.g
              key={t.major.cip}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, x: t.x, y: t.y }}
              exit={{ opacity: 0 }}
              transition={spring}
              className="cursor-pointer"
              onPointerMove={(e) => onHover({ major: t.major, x: e.clientX, y: e.clientY })}
              onPointerLeave={() => onHover(null)}
              onClick={() => onPick(t.major)}
            >
              <motion.rect
                rx={4}
                animate={{ width: t.w, height: t.h, fill }}
                transition={spring}
                stroke="var(--surface)"
                strokeWidth={1.5}
              />
              {showName && (
                <>
                  <text x={8} y={17} fill={ink} style={{ fontSize: 11.5, fontWeight: 600 }}>
                    {clip(t.major.major, t.w)}
                  </text>
                  <text
                    x={8}
                    y={31}
                    fill={ink}
                    fillOpacity={0.82}
                    style={{ fontSize: 10, fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}
                  >
                    {fmtExposure(t.major.exposure)}
                  </text>
                </>
              )}
            </motion.g>
          )
        })}
      </svg>
    </div>
  )
}

function clip(name: string, w: number): string {
  const max = Math.max(3, Math.floor((w - 14) / 6.2))
  return name.length > max ? `${name.slice(0, max - 1)}…` : name
}

/** Very faint full-bleed map, purely texture so the glass panel has something
 *  to refract. Non-interactive and deliberately subordinate to the results. */
function TextureMap({ data, mode }: { data: Major[]; mode: Mode }) {
  const { ref, width, height } = useMeasure<HTMLDivElement>()
  const expC = useMemo(() => exposureColor(mode), [mode])
  const tiles = useMemo(
    () => (width > 0 ? layoutTreemap(data, width, height).tiles : []),
    [data, width, height],
  )
  return (
    <div ref={ref} aria-hidden className="pointer-events-none absolute inset-0 z-0">
      <svg width={width} height={height} className="block opacity-[0.13]">
        {tiles.map((t) => (
          <rect
            key={t.major.cip}
            x={t.x}
            y={t.y}
            width={t.w}
            height={t.h}
            rx={4}
            fill={expC(t.major.exposure)}
            stroke="var(--page)"
            strokeWidth={1.5}
          />
        ))}
      </svg>
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
      <span
        aria-hidden
        className="size-2.5 shrink-0 rounded-full"
        style={{ background: expC(hover.major.exposure) }}
      />
      <span className="truncate font-medium text-ink">{hover.major.major}</span>
      <span className="shrink-0 text-ink3" style={{ fontVariantNumeric: 'tabular-nums' }}>
        {fmtExposure(hover.major.exposure)}
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

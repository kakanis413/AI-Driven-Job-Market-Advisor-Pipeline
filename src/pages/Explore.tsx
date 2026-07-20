import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import AdvisorPanel from '../components/AdvisorPanel'
import HeatmapGrid from '../components/HeatmapGrid'
import LayerToggle, { Segmented } from '../components/LayerToggle'
import { Logo, NavCluster } from '../components/Chrome'
import Legend from '../components/Legend'
import MajorDetailCard from '../components/MajorDetailCard'
import MetersView from '../components/MetersView'
import SearchSpotlight from '../components/SearchSpotlight'
import Tooltip from '../components/Tooltip'
import Treemap from '../components/Treemap'
import { FAMILY_ORDER, REDUCED_TWEEN, SPRING, type Layer, type Mode } from '../design/tokens'
import { advisorIsLive } from '../lib/advisor'
import { useMeasure, useViewportHeight } from '../hooks/useMeasure'
import { layoutTreemap, type Rect } from '../lib/layout'
import type { Page } from '../hooks/useRoute'
import type { Major, TipData } from '../types'

type View = 'map' | 'grid' | 'meters'

interface Props {
  majors: Major[]
  status: 'loading' | 'error' | 'ready'
  url: string
  retry: () => void
  mode: Mode
  nav: (page: Page) => void
  toggle: () => void
  initialQuery?: string
  /** Arriving from a landing tile click: select this major on mount. */
  initialSelectedCip?: string
  /** Arriving from the landing advisor chip: open the advisor on mount. */
  autoAdvisor?: boolean
  initialView: View
}

/** Where the advisor panel morphs from/to, as center-point deltas. */
interface MorphDelta {
  dx: number
  dy: number
  fx: number
  fy: number
}

export default function Explore({
  majors,
  status,
  url,
  retry,
  mode,
  nav,
  toggle,
  initialQuery,
  initialSelectedCip,
  autoAdvisor,
  initialView,
}: Props) {
  const reduce = useReducedMotion()
  const spr = reduce ? REDUCED_TWEEN : SPRING

  const [view, setView] = useState<View>(initialView)
  const [layer, setLayer] = useState<Layer>('exposure')
  const [query, setQuery] = useState(initialQuery ?? '')
  const [selectedCip, setSelectedCip] = useState<string | null>(null)
  const [tip, setTip] = useState<TipData | null>(null)
  const [advisorOpen, setAdvisorOpen] = useState(false)
  const [showChat, setShowChat] = useState(false)
  // The footer always shows the caveat (hard rule 4), so the panel's copy only
  // needs to land once per session; after that it collapses to an ⓘ that peeks.
  const [caveatSeen, setCaveatSeen] = useState(false)
  const [peekCaveat, setPeekCaveat] = useState(false)
  const [delta, setDelta] = useState<MorphDelta>({ dx: 0, dy: 0, fx: 0, fy: 0 })
  const geomRef = useRef(new Map<string, Rect>())

  const vh = useViewportHeight()
  const { ref: vizRef, width: vizW } = useMeasure<HTMLDivElement>()
  // One combined bar now (~57) instead of a header + toolbar, plus the pinned
  // footer (~48) and a little breathing room — so the map gets even more height.
  const mapH = Math.max(480, vh - 150)

  const payExtent = useMemo<[number, number]>(() => {
    const pays = majors.map((m) => m.median_pay).filter((p): p is number => p != null)
    if (pays.length === 0) return [0, 1]
    return [Math.min(...pays), Math.max(...pays)]
  }, [majors])

  const selected = useMemo(
    () => majors.find((m) => m.cip === selectedCip) ?? null,
    [majors, selectedCip],
  )

  /** Open the panel, morphing from `from` (tile or FAB center in client coords). */
  const openAdvisor = useCallback((from?: { x: number; y: number }) => {
    const vw = window.innerWidth
    const vhh = window.innerHeight
    const w = Math.min(400, vw - 32)
    const h = Math.min(640, vhh - 130)
    const cx = vw - 16 - w / 2
    const cy = vhh - 64 - h / 2
    const fab = { x: vw - 20 - 28, y: vhh - 64 - 28 }
    const o = from ?? fab
    setDelta({ dx: o.x - cx, dy: o.y - cy, fx: fab.x - cx, fy: fab.y - cy })
    setAdvisorOpen(true)
  }, [])

  const handleSelect = useCallback(
    (cip: string) => {
      setSelectedCip(cip)
      setQuery('')
      setTip(null)
      setShowChat(false)
      const r = geomRef.current.get(cip)
      const c = vizRef.current?.getBoundingClientRect()
      openAdvisor(r && c ? { x: c.left + r.x + r.w / 2, y: c.top + r.y + r.h / 2 } : undefined)
    },
    [openAdvisor, vizRef],
  )
  const handlePick = useCallback(
    (m: Major) => {
      handleSelect(m.cip)
    },
    [handleSelect],
  )
  const handleTip = useCallback((t: TipData | null) => setTip(t), [])
  const closeAdvisor = useCallback(() => {
    setAdvisorOpen(false)
    setCaveatSeen(true)
    setPeekCaveat(false)
  }, [])
  const caveatVisible = !caveatSeen || peekCaveat

  // Consume the landing → Explore handoff once, after mount: select the clicked
  // major, or just open the advisor if the landing's advisor chip sent us here.
  useEffect(() => {
    if (initialSelectedCip && majors.some((m) => m.cip === initialSelectedCip)) {
      handleSelect(initialSelectedCip)
    } else if (autoAdvisor) {
      setShowChat(true)
      openAdvisor()
    }
    // Intentionally mount-only: the handoff is a one-shot arrival intent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Escape: close the advisor, then clear the selection, then the search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setAdvisorOpen((open) => {
        if (open) return false
        setSelectedCip((cip) => {
          if (cip !== null) return null
          setQuery('')
          return cip
        })
        return open
      })
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const switchView = (v: View) => {
    setTip(null)
    setView(v)
  }

  return (
    <>
      {/* One combined sticky glass bar: logo · search · view · color · legend,
          with nav + dark-mode at the far right. No title band and no second
          row — the page's whole job is the map, so it starts as high as it can.
          The dark fill belongs to the CONTROLS (Segmented); the nav is quiet. */}
      <div className="glass sticky top-0 z-40 border-x-0 border-t-0">
        <div className="mx-auto flex max-w-[1400px] items-center gap-x-3 px-5 py-2.5 md:gap-x-4 md:px-8">
          <Logo mode={mode} onHome={() => nav('landing')} />
          <div className="w-44 shrink-0 sm:w-52 lg:w-60">
            <SearchSpotlight
              compact
              majors={majors}
              mode={mode}
              query={query}
              onQuery={setQuery}
              onPick={handlePick}
            />
          </div>
          <Segmented<View>
            label="View"
            value={view}
            onChange={switchView}
            options={[
              { value: 'map', label: 'Treemap' },
              { value: 'grid', label: 'Heatmap' },
              { value: 'meters', label: 'Value' },
            ]}
          />
          {/* Color layer & legend apply to the tile views, not the value board. */}
          {view !== 'meters' && <LayerToggle layer={layer} onChange={setLayer} />}
          <div className="flex-1" />
          {view !== 'meters' && (
            <div className="hidden shrink-0 lg:block">
              <Legend layer={layer} mode={mode} payExtent={payExtent} />
            </div>
          )}
          <div className="hidden flex-1 lg:block" />
          <NavCluster page="explore" mode={mode} onNav={nav} onToggle={toggle} />
        </div>
      </div>

      <main className="mx-auto mt-3 max-w-[1400px] px-5 md:px-8">
        <div ref={vizRef} className="relative min-w-0">
          {status === 'loading' && vizW > 0 && <SkeletonViz width={vizW} height={mapH} />}
          {status === 'error' && <ErrorCard height={mapH} url={url} retry={retry} />}
          {status === 'ready' && view === 'meters' && (
            <MetersView majors={majors} height={mapH} query={query} onSelect={handleSelect} />
          )}
          {status === 'ready' &&
            vizW > 0 &&
            view === 'map' && (
              <Treemap
                majors={majors}
                width={vizW}
                height={mapH}
                mode={mode}
                layer={layer}
                payExtent={payExtent}
                query={query}
                selectedCip={selectedCip}
                onSelect={handleSelect}
                onTip={handleTip}
                geomRef={geomRef}
              />
            )}
          {status === 'ready' && vizW > 0 && view === 'grid' && (
            <HeatmapGrid
              majors={majors}
              width={vizW}
              mode={mode}
              layer={layer}
              payExtent={payExtent}
              selectedCip={selectedCip}
              onSelect={handleSelect}
              onTip={handleTip}
              geomRef={geomRef}
            />
          )}
        </div>
      </main>

      {/* Advisor launcher: a circle that morphs into the panel. */}
      <AnimatePresence>
        {!advisorOpen && (
          <motion.button
            key="fab"
            onClick={() => {
              setShowChat(true)
              openAdvisor()
            }}
            aria-label="Ask the advisor"
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.4, opacity: 0, transition: { duration: 0.15 } }}
            transition={spr}
            whileTap={reduce ? undefined : { scale: 0.96 }}
            className="group fixed bottom-16 right-5 z-40 flex items-center rounded-full bg-ink text-page shadow-lg shadow-black/25 ring-1 ring-black/5 transition-shadow duration-200 hover:shadow-xl hover:shadow-black/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page"
          >
            {/* Label reveals on hover/focus so the purpose is read, not guessed.
                It sits left of the icon so the icon stays pinned to the corner. */}
            <span
              className={`max-w-0 overflow-hidden whitespace-nowrap text-[14px] font-semibold opacity-0 ${
                reduce ? '' : 'transition-all duration-200 ease-out'
              } group-hover:max-w-[150px] group-hover:pl-5 group-hover:opacity-100 group-focus-visible:max-w-[150px] group-focus-visible:pl-5 group-focus-visible:opacity-100`}
            >
              Ask the advisor
            </span>
            <span aria-hidden className="grid size-[58px] shrink-0 place-items-center">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 3.2a8 8 0 0 1 8 8c0 4.42-3.58 8-8 8-1.05 0-2.06-.2-2.98-.58L4 20l1.4-3.86A8 8 0 0 1 12 3.2Z"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinejoin="round"
                />
                <path
                  d="M8.6 11.6h.01M12 11.6h.01M15.4 11.6h.01"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                />
              </svg>
            </span>
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {advisorOpen && (
          <motion.div
            key="advisor-panel"
            role="dialog"
            aria-label={selected ? `Details and advisor for ${selected.major}` : 'AI advisor'}
            initial={
              reduce
                ? { opacity: 0 }
                : { x: delta.dx, y: delta.dy, scale: 0.1, opacity: 0.5, borderRadius: 999 }
            }
            animate={{ x: 0, y: 0, scale: 1, opacity: 1, borderRadius: 20 }}
            exit={
              reduce
                ? { opacity: 0 }
                : { x: delta.fx, y: delta.fy, scale: 0.08, opacity: 0, borderRadius: 999 }
            }
            transition={spr}
            className="glass fixed bottom-16 right-4 z-50 flex flex-col overflow-hidden rounded-panel shadow-2xl shadow-black/25"
            style={{
              width: 'min(400px, calc(100vw - 2rem))',
              height: 'min(640px, calc(100dvh - 130px))',
            }}
          >
            <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-ink">
                  {selected ? selected.major : 'AI advisor'}
                </div>
                {selected && <div className="micro text-ink3">{selected.family}</div>}
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <span className="micro inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-ink3">
                  <span
                    aria-hidden
                    className="size-1.5 rounded-full"
                    style={{ background: advisorIsLive ? '#0ca30c' : '#d99a2b' }}
                  />
                  {advisorIsLive ? 'Live' : 'Offline preview'}
                </span>
                {caveatSeen && (
                  <button
                    onClick={() => setPeekCaveat((v) => !v)}
                    aria-label="What does exposure mean?"
                    aria-expanded={peekCaveat}
                    className="grid size-6 place-items-center rounded-full border border-line text-[11px] font-semibold text-ink3 transition-colors hover:text-ink"
                  >
                    i
                  </button>
                )}
                <button
                  onClick={closeAdvisor}
                  aria-label="Close advisor"
                  className="grid size-7 place-items-center rounded-md text-ink3 transition-colors hover:bg-raised hover:text-ink"
                >
                  <svg width="12" height="12" viewBox="0 0 13 13" fill="none" aria-hidden>
                    <path d="M2 2l9 9M11 2l-9 9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Caveat lands once per session, then collapses to the ⓘ above.
                Hard rule 4 is still satisfied by the always-on footer caveat. */}
            <AnimatePresence initial={false}>
              {caveatVisible && (
                <motion.p
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden border-b border-line bg-accent-soft/60 px-4 py-2 text-[11.5px] leading-snug text-ink2"
                >
                  High exposure does <b className="font-semibold text-ink">not</b> mean the job
                  disappears — it means the mix of tasks is likely to change.
                </motion.p>
              )}
            </AnimatePresence>

            {showChat || !selected ? (
              <div className="min-h-0 flex-1">
                <AdvisorPanel key={selected?.cip ?? 'general'} major={selected} />
              </div>
            ) : (
              <>
                <div className="min-h-0 flex-1 overflow-y-auto p-3">
                  <MajorDetailCard major={selected} mode={mode} />
                </div>
                <div className="border-t border-line p-3">
                  <button
                    onClick={() => setShowChat(true)}
                    className="w-full rounded-md bg-ink px-4 py-2 text-sm font-semibold text-surface transition-opacity hover:opacity-90"
                  >
                    Ask the advisor about this major
                  </button>
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <Tooltip tip={tip} mode={mode} />
    </>
  )
}

/** Loading state: a skeleton treemap in real layout proportions, shimmering. */
function SkeletonViz({ width, height }: { width: number; height: number }) {
  const fakes = useMemo<Major[]>(() => {
    const weights = [34, 21, 18, 14, 12, 10, 9, 8, 7, 6, 5, 5, 4, 4, 3, 3]
    return weights.map((completions, i) => ({
      cip: `sk-${i}`,
      major: '',
      family: FAMILY_ORDER[i % FAMILY_ORDER.length],
      completions,
      exposure: 0,
      median_pay: 0,
      growth: 'average',
      occupations: [],
      rationale: '',
    }))
  }, [])
  const { tiles } = useMemo(() => layoutTreemap(fakes, width, height), [fakes, width, height])
  return (
    <svg width={width} height={height} role="img" aria-label="Loading majors…">
      {tiles.map((t, i) => (
        <motion.rect
          key={t.major.cip}
          x={t.x}
          y={t.y}
          width={t.w}
          height={t.h}
          rx={4}
          fill="var(--line)"
          animate={{ opacity: [0.4, 0.75, 0.4] }}
          transition={{ duration: 1.6, repeat: Infinity, delay: i * 0.06 }}
        />
      ))}
    </svg>
  )
}

function ErrorCard({ height, url, retry }: { height: number; url: string; retry: () => void }) {
  return (
    <div style={{ height }} className="grid place-items-center">
      <div className="w-full max-w-md rounded-card border border-line bg-surface p-6 text-center">
        <div className="micro text-ink3">Data unavailable</div>
        <p className="mt-2 text-sm leading-relaxed text-ink2">
          Couldn’t load{' '}
          <code className="rounded bg-raised px-1.5 py-0.5 text-[12px] text-ink">{url}</code>. Check
          that the file exists and matches the data contract.
        </p>
        <button
          onClick={retry}
          className="mt-4 h-9 rounded-[10px] bg-ink px-4 text-[13px] font-medium text-page transition-opacity hover:opacity-90"
        >
          Try again
        </button>
      </div>
    </div>
  )
}

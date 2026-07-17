import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import AdvisorPanel from '../components/AdvisorPanel'
import HeatmapGrid from '../components/HeatmapGrid'
import LayerToggle, { Segmented } from '../components/LayerToggle'
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
import type { Major, TipData } from '../types'

type View = 'map' | 'grid' | 'meters'

interface Props {
  majors: Major[]
  status: 'loading' | 'error' | 'ready'
  url: string
  retry: () => void
  mode: Mode
  initialView: View
}

/** Where the advisor panel morphs from/to, as center-point deltas. */
interface MorphDelta {
  dx: number
  dy: number
  fx: number
  fy: number
}

export default function Explore({ majors, status, url, retry, mode, initialView }: Props) {
  const reduce = useReducedMotion()
  const spr = reduce ? REDUCED_TWEEN : SPRING

  const [view, setView] = useState<View>(initialView)
  const [layer, setLayer] = useState<Layer>('exposure')
  const [query, setQuery] = useState('')
  const [selectedCip, setSelectedCip] = useState<string | null>(null)
  const [tip, setTip] = useState<TipData | null>(null)
  const [advisorOpen, setAdvisorOpen] = useState(false)
  const [showChat, setShowChat] = useState(false)
  const [delta, setDelta] = useState<MorphDelta>({ dx: 0, dy: 0, fx: 0, fy: 0 })
  const geomRef = useRef(new Map<string, Rect>())

  const vh = useViewportHeight()
  const { ref: vizRef, width: vizW } = useMeasure<HTMLDivElement>()
  // The advisor is a floating circle now — the map owns the full width/height.
  const mapH = Math.max(480, vh - 310)

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
  const closeAdvisor = useCallback(() => setAdvisorOpen(false), [])

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
      <section className="mx-auto max-w-[1400px] px-5 pt-6 md:px-8">
        <h1 className="text-[22px] font-semibold tracking-tight text-ink">Explore the map</h1>
        <p className="mt-1 text-[13.5px] text-ink2">
          Tiles sized by graduates. Search your major, or click any tile to ask the advisor.
        </p>
        <div className="mt-5 flex flex-wrap items-end gap-x-5 gap-y-3">
          <div className="w-full sm:max-w-sm">
            <SearchSpotlight
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
          {view !== 'meters' && (
            <>
              <LayerToggle layer={layer} onChange={setLayer} />
              <div className="ms-auto">
                <Legend layer={layer} mode={mode} payExtent={payExtent} />
              </div>
            </>
          )}
        </div>
      </section>

      <main className="mx-auto mt-4 max-w-[1400px] px-5 md:px-8">
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
            aria-label="Open the AI advisor"
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.4, opacity: 0, transition: { duration: 0.15 } }}
            transition={spr}
            whileHover={reduce ? undefined : { scale: 1.08 }}
            whileTap={reduce ? undefined : { scale: 0.94 }}
            className="fixed bottom-16 right-5 z-40 grid size-14 place-items-center rounded-full bg-ink text-page shadow-xl shadow-black/20"
          >
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden>
              <path
                d="M11 3a7.5 7.5 0 0 1 7.5 7.5c0 4.14-3.36 7.5-7.5 7.5-1.02 0-2-.2-2.88-.58L4 19l1.02-3.7A7.5 7.5 0 1 1 11 3Z"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinejoin="round"
              />
              <path d="M7.8 11h.01M11 11h.01M14.2 11h.01" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
            </svg>
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
            className="fixed bottom-16 right-4 z-50 flex flex-col overflow-hidden border border-line bg-surface shadow-2xl shadow-black/25"
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
              <div className="flex shrink-0 items-center gap-2">
                <span className="micro inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-ink3">
                  <span
                    aria-hidden
                    className="size-1.5 rounded-full"
                    style={{ background: advisorIsLive ? '#0ca30c' : '#d99a2b' }}
                  />
                  {advisorIsLive ? 'Live' : 'Offline preview'}
                </span>
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

            {/* The caveat stays visible — hard rule 4. */}
            <p className="border-b border-line bg-accent-soft/60 px-4 py-2 text-[11.5px] leading-snug text-ink2">
              High exposure does <b className="font-semibold text-ink">not</b> mean the job
              disappears — it means the mix of tasks is likely to change.
            </p>

            {showChat || !selected ? (
              <div className="min-h-0 flex-1">
                <AdvisorPanel key={selected?.cip ?? 'general'} major={selected} />
              </div>
            ) : (
              <div className="min-h-0 flex-1 overflow-y-auto p-3">
                <MajorDetailCard major={selected} mode={mode} />
              </div>
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

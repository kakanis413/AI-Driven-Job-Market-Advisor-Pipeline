import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import AdvisorPanel from '../components/AdvisorPanel'
import HeatmapGrid from '../components/HeatmapGrid'
import { CloseIcon } from '../components/icons'
import LayerToggle, { Segmented } from '../components/LayerToggle'
import { Logo, NavCluster } from '../components/Chrome'
import Legend from '../components/Legend'
import MajorDetailCard from '../components/MajorDetailCard'
import SearchSpotlight from '../components/SearchSpotlight'
import StatsStrip, { STATS_STRIP_H } from '../components/StatsStrip'
import Tooltip from '../components/Tooltip'
import Treemap from '../components/Treemap'
import { FOCUS_RING_ON_PAGE } from '../design/classes'
import { FAMILY_ORDER, REDUCED_TWEEN, SPRING, type Layer, type Mode } from '../design/tokens'
import { advisorIsLive } from '../lib/advisor'
import { exposureColor, fmtCount, fmtExposure, fmtPay, growthOf, normalize } from '../design/scales'
import { useMeasure, useMediaQuery, useViewportHeight } from '../hooks/useMeasure'
import { layoutTreemap, type Rect } from '../lib/layout'
import type { Page } from '../hooks/useRoute'
import type { Major, TipData } from '../types'

type View = 'map' | 'grid'

interface Props {
  majors: Major[]
  status: 'loading' | 'error' | 'ready'
  url: string
  retry: () => void
  mode: Mode
  nav: (page: Page, sub?: string) => void
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

  // Tiles are unreadable at phone widths, so a fresh Explore on a narrow
  // viewport opens on the Table instead of the treemap. This is only the mount
  // default — read once, never reactive — so it never yanks a view the user
  // later picks with the toggle. An explicit `grid` route already wins here.
  const [view, setView] = useState<View>(() =>
    initialView === 'map' && matchMedia('(max-width: 639px)').matches ? 'grid' : initialView,
  )
  const [layer, setLayer] = useState<Layer>('exposure')
  const [query, setQuery] = useState(initialQuery ?? '')
  const [selectedCip, setSelectedCip] = useState<string | null>(null)
  const [tip, setTip] = useState<TipData | null>(null)
  // Touch/phone users can't hover, so a tile tap has nothing to preview before
  // the advisor takes over the screen. On a coarse pointer OR a narrow viewport
  // a tap opens a lightweight bottom sheet with the same data the tooltip shows,
  // then hands off to the advisor on request. (Coarse-pointer detection alone
  // misses some phones, so width is an OR fallback — a comma is media-query OR.)
  const tapPreview = useMediaQuery('(pointer: coarse), (max-width: 639px)')
  const [previewCip, setPreviewCip] = useState<string | null>(null)
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
  // Glass chrome is up to ~186 tall (controls + inline legend, with the nav
  // wrapping to its own line on mid-width screens, plus the tightened search
  // row); subtract that, the pinned footer (~48), and a little breathing room so
  // the map always clears the footer at every breakpoint.
  // The stats strip only shows from lg up: below that it would wrap into four
  // ragged rows and eat the map, and narrow viewports already open on Table.
  const showStats = useMediaQuery('(min-width: 1024px)')
  const mapH = Math.max(480, vh - 218 - (showStats ? STATS_STRIP_H : 0))

  const payExtent = useMemo<[number, number]>(() => {
    const pays = majors.map((m) => m.median_pay).filter((p): p is number => p != null)
    if (pays.length === 0) return [0, 1]
    return [Math.min(...pays), Math.max(...pays)]
  }, [majors])

  const selected = useMemo(
    () => majors.find((m) => m.cip === selectedCip) ?? null,
    [majors, selectedCip],
  )
  const preview = useMemo(
    () => majors.find((m) => m.cip === previewCip) ?? null,
    [majors, previewCip],
  )

  // Live count of majors matching the active query — same predicate the viz
  // uses to dim non-matches, so the number the user reads matches what they see.
  const trimmedQuery = query.trim()
  const matchCount = useMemo(() => {
    const q = normalize(query)
    if (!q) return 0
    return majors.filter((m) => normalize(m.major).includes(q) || normalize(m.family).includes(q))
      .length
  }, [majors, query])

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
  // Tile taps from the viz: on touch (and only when the advisor isn't already
  // open) show the preview sheet first; otherwise fall straight through to the
  // advisor as before. Keyboard/mouse selection is unaffected.
  const handleTileSelect = useCallback(
    (cip: string) => {
      if (tapPreview && !advisorOpen) {
        setTip(null)
        setPreviewCip(cip)
      } else {
        handleSelect(cip)
      }
    },
    [tapPreview, advisorOpen, handleSelect],
  )
  const closePreview = useCallback(() => setPreviewCip(null), [])
  const askAdvisorFromPreview = useCallback(() => {
    setPreviewCip((cip) => {
      if (cip) handleSelect(cip)
      return null
    })
  }, [handleSelect])
  const handleTip = useCallback((t: TipData | null) => setTip(t), [])
  // Closing releases the selection too — otherwise the treemap tile stayed
  // ringed as "selected" forever, and reopening the FAB silently resumed the
  // same major instead of starting fresh. Same reasoning for showChat: the
  // next open should land on the neutral card/chat, not a stale mid-chat view.
  const closeAdvisor = useCallback(() => {
    setAdvisorOpen(false)
    setSelectedCip(null)
    setShowChat(false)
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

  // Escape: close the preview sheet, then the advisor (which now also releases
  // the selection — see closeAdvisor), then the search. Kept as separate steps
  // so hitting Escape once never wipes more than the topmost thing open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (previewCip !== null) {
        setPreviewCip(null)
        return
      }
      if (advisorOpen) {
        closeAdvisor()
        return
      }
      setQuery('')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [previewCip, advisorOpen, closeAdvisor])

  const switchView = (v: View) => {
    setTip(null)
    setView(v)
  }

  return (
    <>
      {/* Sticky glass chrome, two rows so Explore reads as one system with News:
          a top bar identical to the News header (logo left · nav + dark-mode
          right), then the tool row (search · view · color · legend) hairlined
          off below it. The dark fill belongs to the CONTROLS (Segmented); the
          nav stays quiet. */}
      <div className="glass sticky top-0 z-40 border-x-0 border-t-0">
        <div className="mx-auto max-w-[1400px] px-5 md:px-8">
          {/* Row 1 — the controls ride next to the wordmark; nav trails right.
              The second slot always holds exactly one Segmented (Color by for the
              tile views, Sort by for the value board), same size and position, so
              switching tabs never reflows the bar. */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 py-2.5">
            <Logo mode={mode} onHome={() => nav('landing')} context="Explore" />
            <Segmented<View>
              label="View"
              value={view}
              onChange={switchView}
              options={[
                { value: 'map', label: 'Treemap' },
                { value: 'grid', label: 'Table' },
              ]}
            />
            <LayerToggle layer={layer} onChange={setLayer} />
            {/* Reference sits with the controls: the color legend for the tile
                views. Shown from xl up, where row 1 has room for it beside the
                controls; below that it stays out so the bar never crowds. */}
            <div className="hidden shrink-0 xl:block">
              <Legend layer={layer} mode={mode} payExtent={payExtent} />
            </div>
            {/* ms-auto (not a flex-1 spacer) so that when the row wraps on a
                narrow viewport the nav drops to the bottom-right, never under
                the logo. */}
            <div className="ms-auto">
              <NavCluster page="explore" mode={mode} onNav={nav} onToggle={toggle} />
            </div>
          </div>
          {/* Row 2 — search, roomy and full-width, with the compact reference
              trailing right. The color encoding must never be unreadable, so
              below xl (where row 1 drops the inline legend) it reappears here:
              the compact color scale for the tile views, the value caption for
              the board. At xl this row is search only — the inline legend in
              row 1 takes over. */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line py-1.5">
            <div className="w-full max-w-[560px]">
              <SearchSpotlight
                compact
                majors={majors}
                mode={mode}
                query={query}
                onQuery={setQuery}
                onPick={handlePick}
              />
            </div>
            {/* Match feedback while a query is active — mirrors the landing's
                no-match copy. Live region so the count is announced as it
                changes. */}
            {trimmedQuery && (
              <p role="status" aria-live="polite" className="text-[12.5px] text-ink3">
                {matchCount === 0 ? (
                  <>
                    No majors match <span className="text-ink2">“{trimmedQuery}”</span>
                  </>
                ) : (
                  <>
                    <span
                      className="font-semibold text-ink2"
                      style={{ fontVariantNumeric: 'tabular-nums' }}
                    >
                      {matchCount}
                    </span>{' '}
                    {matchCount === 1 ? 'major matches' : 'majors match'}
                  </>
                )}
              </p>
            )}
            <div className="ms-auto xl:hidden">
              <Legend compact layer={layer} mode={mode} payExtent={payExtent} />
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto mt-3 max-w-[1400px] px-5 md:px-8">
        {/* The read-out sits above the map for both tile views. */}
        {status === 'ready' && showStats && (
          <div className="mb-3">
            <StatsStrip majors={majors} layer={layer} mode={mode} payExtent={payExtent} />
          </div>
        )}
        <div ref={vizRef} className="relative min-w-0">
          {status === 'loading' && vizW > 0 && <SkeletonViz width={vizW} height={mapH} />}
          {status === 'error' && <ErrorCard height={mapH} url={url} retry={retry} />}
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
                onSelect={handleTileSelect}
                onTip={handleTip}
                geomRef={geomRef}
              />
            )}
          {status === 'ready' && vizW > 0 && view === 'grid' && (
            <HeatmapGrid
              majors={majors}
              width={vizW}
              height={mapH}
              mode={mode}
              layer={layer}
              payExtent={payExtent}
              selectedCip={selectedCip}
              onSelect={handleTileSelect}
              onTip={handleTip}
              geomRef={geomRef}
            />
          )}
        </div>
      </div>

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
            className={`group fixed bottom-16 right-5 z-40 flex items-center rounded-full bg-ink text-page shadow-lg shadow-black/25 ring-1 ring-black/5 transition-shadow duration-200 hover:shadow-xl hover:shadow-black/30 ${FOCUS_RING_ON_PAGE}`}
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
                  {selected ? selected.major : 'AI career advisor'}
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
                  <CloseIcon />
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
                <div className="space-y-2 border-t border-line p-3">
                  <button
                    onClick={() => setShowChat(true)}
                    className="w-full rounded-md bg-ink px-4 py-2 text-sm font-semibold text-surface transition-opacity hover:opacity-90"
                  >
                    Ask the advisor about this major
                  </button>
                  {/* Bridge to the roomy home: carry this major into /chat, where
                      the school context and national-estimates rail live. */}
                  <button
                    onClick={() => nav('chat', selected.cip)}
                    className="w-full rounded-md px-4 py-2 text-[13px] font-medium text-ink2 transition-colors hover:text-ink"
                  >
                    Open in the full chat →
                  </button>
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <Tooltip tip={tip} mode={mode} />

      {/* Touch preview: the tooltip's data as a dismissible bottom sheet, with a
          hand-off to the advisor. Sits above the pinned footer so hard rule 4's
          caveat stays visible. */}
      <PreviewSheet
        major={preview}
        mode={mode}
        reduce={!!reduce}
        onClose={closePreview}
        onAsk={askAdvisorFromPreview}
      />
    </>
  )
}

/** Bottom-sheet preview for touch: the same figures the hover tooltip shows,
 *  plus a hand-off to the advisor. Dismissible via the scrim, the close button,
 *  or Escape (handled in Explore). Floats above the footer so the caveat stays
 *  visible (hard rule 4). */
function PreviewSheet({
  major,
  mode,
  reduce,
  onClose,
  onAsk,
}: {
  major: Major | null
  mode: Mode
  reduce: boolean
  onClose: () => void
  onAsk: () => void
}) {
  const sheetRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (major) sheetRef.current?.focus()
  }, [major])

  const growth = major && growthOf(major.growth)
  return (
    <AnimatePresence>
      {major && growth && (
        <>
          <motion.button
            key="preview-scrim"
            aria-label="Dismiss preview"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 cursor-default"
            style={{ background: 'color-mix(in srgb, var(--ink) 28%, transparent)' }}
          />
          <motion.div
            key="preview-sheet"
            ref={sheetRef}
            role="dialog"
            aria-modal="true"
            aria-label={`${major.major} — quick facts`}
            tabIndex={-1}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: '110%' }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: '110%' }}
            transition={reduce ? REDUCED_TWEEN : SPRING}
            className="glass fixed inset-x-3 bottom-16 z-50 mx-auto max-w-[560px] rounded-panel p-4 shadow-2xl shadow-black/25 focus:outline-none"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="title text-ink">{major.major}</div>
                <div className="micro mt-0.5 text-ink3">{major.family}</div>
              </div>
              <button
                onClick={onClose}
                aria-label="Close preview"
                className="grid size-7 shrink-0 place-items-center rounded-md text-ink3 transition-colors hover:bg-raised hover:text-ink"
              >
                <CloseIcon />
              </button>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
              <SheetMetric label="AI exposure">
                <span
                  aria-hidden
                  className="mr-1.5 inline-block size-2.5 rounded-full align-[-1px]"
                  style={{ background: exposureColor(mode)(major.exposure) }}
                />
                <b style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtExposure(major.exposure)}</b>
                <span className="text-ink3"> /10</span>
              </SheetMetric>
              <SheetMetric label="Median pay">
                <b style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtPay(major.median_pay)}</b>
              </SheetMetric>
              <SheetMetric label="Bachelor's grads / yr">
                <b style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtCount(major.completions)}</b>
              </SheetMetric>
              <SheetMetric label="Job growth">
                <span aria-hidden>{growth.glyph} </span>
                <b>{growth.label}</b>
              </SheetMetric>
            </div>

            <p className="mt-3 border-t border-line pt-3 text-[12.5px] leading-relaxed text-ink2">
              {major.rationale}
            </p>

            <button
              onClick={onAsk}
              className="mt-3 w-full rounded-md bg-ink px-4 py-2.5 text-sm font-semibold text-page transition-opacity hover:opacity-90"
            >
              Ask the advisor about this major
            </button>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

function SheetMetric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="micro text-ink3">{label}</div>
      <div className="mt-0.5 text-[13px] text-ink">{children}</div>
    </div>
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

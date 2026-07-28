/** The instrument strip — a live read-out of the whole distribution that sits
 *  above the map and fully recomputes when the layer changes.
 *
 *  A treemap alone shows shape but states nothing. The strip is what turns the
 *  page from a picture into an argument: it carries the weighted headline, the
 *  distribution, the tier split, and — the part that matters — two CROSS-TABS.
 *  Exposure against pay and against pay-to-debt is the finding a student can't
 *  get anywhere else, and it is counterintuitive: exposure climbs with pay
 *  (6.2 at the bottom band, 8.7 at the top) and with ROI. The map can't say
 *  that; these two blocks can.
 *
 *  Everything is GRADUATE-WEIGHTED, never a plain average over majors. A mean
 *  across 360 majors would let a 3-graduate program count as much as a 170,000-
 *  graduate one and quietly misstate the cohort. */

import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { FOCUS_RING_ON_PAGE } from '../design/classes'
import {
  exposureColor,
  fmtCount,
  fmtExposure,
  fmtPay,
  payColor,
} from '../design/scales'
import { EASE, type Layer, type Mode } from '../design/tokens'
import type { Major } from '../types'

/** Reserved height, mirrored in Explore's `mapH` budget so adding the strip
 *  never pushes the map under the pinned footer. */
export const STATS_STRIP_H = 104

interface Props {
  majors: Major[]
  layer: Layer
  mode: Mode
  payExtent: [number, number]
}

/* ---------- banding ---------- */

/** Pay bands chosen from the observed quartiles (p25 $45.6k, median $54k,
 *  p75 $71.3k) so every band holds a real share of the cohort — 19/38/19/21/2 —
 *  rather than round numbers that leave buckets empty. */
const PAY_BANDS = [
  { label: '<$45k', lo: 0, hi: 45_000 },
  { label: '$45–60k', lo: 45_000, hi: 60_000 },
  { label: '$60–75k', lo: 60_000, hi: 75_000 },
  { label: '$75–95k', lo: 75_000, hi: 95_000 },
  { label: '$95k+', lo: 95_000, hi: Infinity },
]

/** Pay-to-debt bands. The median major returns $2.53 of early-career pay per $1
 *  of typical debt, so the split sits either side of that. */
const ROI_BANDS = [
  { label: '<1.5×', lo: 0, hi: 1.5 },
  { label: '1.5–2.5×', lo: 1.5, hi: 2.5 },
  { label: '2.5–3.5×', lo: 2.5, hi: 3.5 },
  { label: '3.5×+', lo: 3.5, hi: Infinity },
]

/** Exposure tiers — the same three bands `exposureBand` uses for prose, so the
 *  strip and the detail card never label the same score differently. */
const EXPOSURE_TIERS = [
  { label: 'Barely touched', sub: '0–3', lo: 0, hi: 4 },
  { label: 'Reshaped', sub: '4–7', lo: 4, hi: 8 },
  { label: 'Rewired', sub: '8–10', lo: 8, hi: 10.001 },
]

/* ---------- aggregation ---------- */

const gradsOf = (m: Major) => m.completions || 0

/** Graduate-weighted mean of `metric` over the majors passing `where`. */
function weighted(
  majors: Major[],
  metric: (m: Major) => number | null,
  where: (m: Major) => boolean = () => true,
): { avg: number; grads: number } {
  let sum = 0
  let grads = 0
  for (const m of majors) {
    const v = metric(m)
    const g = gradsOf(m)
    if (v == null || g <= 0 || !where(m)) continue
    sum += v * g
    grads += g
  }
  return { avg: grads > 0 ? sum / grads : 0, grads }
}

const inBand = (v: number | null | undefined, lo: number, hi: number) =>
  v != null && v >= lo && v < hi

/* ---------- component ---------- */

export default function StatsStrip({ majors, layer, mode, payExtent }: Props) {
  const expC = useMemo(() => exposureColor(mode), [mode])
  const payC = useMemo(() => payColor(mode, payExtent), [mode, payExtent])

  // The histogram/tiers/cross-tabs are real, well-reasoned data, but all six
  // blocks at once is a lot to take in before a reader has even looked at the
  // map. Cohort/headline/impact stay the always-visible read; the rest lives
  // in an on-demand popover so the reserved height (STATS_STRIP_H, which
  // Explore's mapH budget is built around) never changes with expand state —
  // the panel floats over the map instead of pushing it down.
  const reduce = useReducedMotion()
  const [detailOpen, setDetailOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!detailOpen) return
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setDetailOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      setDetailOpen(false)
      btnRef.current?.focus()
    }
    window.addEventListener('pointerdown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('pointerdown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [detailOpen])

  const stats = useMemo(() => {
    const totalGrads = majors.reduce((s, m) => s + gradsOf(m), 0)
    const exposure = (m: Major) => m.exposure
    const pay = (m: Major) => m.median_pay

    const headline = weighted(majors, layer === 'exposure' ? exposure : pay)

    // Distribution: graduates per whole-point exposure bucket, or per pay band.
    const histogram =
      layer === 'exposure'
        ? Array.from({ length: 9 }, (_, i) => {
            const score = i + 1
            const grads = majors
              .filter((m) => inBand(m.exposure, score, score + 1))
              .reduce((s, m) => s + gradsOf(m), 0)
            return { key: String(score), grads, fill: expC(score + 0.5) }
          })
        : PAY_BANDS.map((b) => {
            const grads = majors
              .filter((m) => inBand(m.median_pay, b.lo, b.hi))
              .reduce((s, m) => s + gradsOf(m), 0)
            return {
              key: b.label,
              grads,
              fill: payC(Math.min(b.hi === Infinity ? payExtent[1] : b.hi, payExtent[1])),
            }
          })

    // Tiers: share of the cohort in each band of the active layer.
    const tiers =
      layer === 'exposure'
        ? EXPOSURE_TIERS.map((t) => ({
            label: t.label,
            sub: t.sub,
            grads: majors
              .filter((m) => inBand(m.exposure, t.lo, t.hi))
              .reduce((s, m) => s + gradsOf(m), 0),
            fill: expC((t.lo + Math.min(t.hi, 10)) / 2),
          }))
        : PAY_BANDS.map((b) => ({
            label: b.label,
            sub: '',
            grads: majors
              .filter((m) => inBand(m.median_pay, b.lo, b.hi))
              .reduce((s, m) => s + gradsOf(m), 0),
            fill: payC(Math.min(b.hi === Infinity ? payExtent[1] : b.hi, payExtent[1])),
          }))

    // The two cross-tabs. On the exposure layer these are the payload: they
    // show exposure climbing with both pay and ROI.
    const crossA =
      layer === 'exposure'
        ? {
            title: 'Exposure × pay',
            rows: PAY_BANDS.map((b) => {
              const { avg } = weighted(majors, exposure, (m) =>
                inBand(m.median_pay, b.lo, b.hi),
              )
              return { label: b.label, value: fmtExposure(avg), pct: (avg / 10) * 100, fill: expC(avg) }
            }),
          }
        : {
            title: 'Pay × exposure',
            rows: EXPOSURE_TIERS.map((t) => {
              const { avg } = weighted(majors, pay, (m) => inBand(m.exposure, t.lo, t.hi))
              return {
                label: t.sub,
                value: fmtPay(avg),
                pct: (avg / Math.max(1, payExtent[1])) * 100,
                fill: payC(avg),
              }
            }),
          }

    const crossB =
      layer === 'exposure'
        ? {
            title: 'Exposure × pay-to-debt',
            rows: ROI_BANDS.map((b) => {
              const { avg } = weighted(majors, exposure, (m) => inBand(m.payToDebt, b.lo, b.hi))
              return { label: b.label, value: fmtExposure(avg), pct: (avg / 10) * 100, fill: expC(avg) }
            }),
          }
        : {
            title: 'Pay × pay-to-debt',
            rows: ROI_BANDS.map((b) => {
              const { avg } = weighted(majors, pay, (m) => inBand(m.payToDebt, b.lo, b.hi))
              return {
                label: b.label,
                value: fmtPay(avg),
                pct: (avg / Math.max(1, payExtent[1])) * 100,
                fill: payC(avg),
              }
            }),
          }

    // The impact number — the one figure meant to be remembered and quoted.
    const impact =
      layer === 'exposure'
        ? {
            title: 'Most exposed',
            value: fmtCount(
              majors.filter((m) => (m.exposure ?? 0) >= 7).reduce((s, m) => s + gradsOf(m), 0),
            ),
            note: 'grads/yr in majors scoring 7+',
            fill: expC(8),
          }
        : {
            title: 'Under $50k',
            value: fmtCount(
              majors
                .filter((m) => m.median_pay != null && m.median_pay < 50_000)
                .reduce((s, m) => s + gradsOf(m), 0),
            ),
            note: 'grads/yr below $50k median',
            fill: payC(payExtent[0]),
          }

    return { totalGrads, headline, histogram, tiers, crossA, crossB, impact }
  }, [majors, layer, expC, payC, payExtent])

  const maxHist = Math.max(1, ...stats.histogram.map((h) => h.grads))

  return (
    <div
      ref={rootRef}
      className="relative flex flex-wrap items-start gap-x-7 gap-y-3 border-b border-line pb-3"
      style={{ minHeight: STATS_STRIP_H }}
    >
      <Block title="Cohort">
        <Big>{fmtCount(stats.totalGrads)}</Big>
        <Note>bachelor&apos;s grads/yr · {majors.length} majors</Note>
      </Block>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={layer}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="flex flex-wrap items-start gap-x-7 gap-y-3"
        >
          <Block title={layer === 'exposure' ? 'Avg. exposure' : 'Avg. median pay'}>
            <Big>
              {layer === 'exposure'
                ? fmtExposure(stats.headline.avg)
                : fmtPay(stats.headline.avg)}
            </Big>
            <Note>
              grad-weighted{layer === 'exposure' ? ' · 0–10' : ''}
            </Note>
          </Block>

          <Block title={stats.impact.title}>
            <Big style={{ color: stats.impact.fill }}>{stats.impact.value}</Big>
            <Note>{stats.impact.note}</Note>
          </Block>
        </motion.div>
      </AnimatePresence>

      <button
        ref={btnRef}
        onClick={() => setDetailOpen((v) => !v)}
        aria-expanded={detailOpen}
        aria-haspopup="dialog"
        className={`micro ml-auto self-center shrink-0 rounded-md px-1.5 py-1 text-ink3 transition-colors hover:text-ink ${FOCUS_RING_ON_PAGE}`}
      >
        {detailOpen ? 'Less detail' : 'More detail'}
      </button>

      <AnimatePresence>
        {detailOpen && (
          <motion.div
            role="dialog"
            aria-label="Distribution detail"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            transition={{ duration: reduce ? 0.12 : 0.18, ease: EASE }}
            className="glass absolute inset-x-0 top-full z-30 mt-2 flex flex-wrap items-start gap-x-7 gap-y-3 rounded-card p-3 shadow-xl"
          >
            <Block title={layer === 'exposure' ? 'Grads by exposure' : 'Grads by pay'}>
              <div className="flex h-[42px] items-end gap-[2px]" aria-hidden>
                {stats.histogram.map((h) => (
                  <div
                    key={h.key}
                    className="w-[9px] rounded-t-[1px]"
                    style={{
                      height: `${Math.max(2, (h.grads / maxHist) * 100)}%`,
                      background: h.fill,
                    }}
                  />
                ))}
              </div>
              <Note>
                {layer === 'exposure' ? '1 → 9' : `${PAY_BANDS[0].label} → ${PAY_BANDS[4].label}`}
              </Note>
            </Block>

            <Block title={layer === 'exposure' ? 'Exposure tiers' : 'Pay tiers'}>
              <div className="flex flex-col gap-[3px]">
                {stats.tiers.map((t) => (
                  <div key={t.label} className="flex items-center gap-1.5 text-[11.5px] leading-none">
                    <span
                      className="size-[9px] shrink-0 rounded-[2px]"
                      style={{ background: t.fill }}
                    />
                    <span className="w-[86px] shrink-0 truncate text-ink3">{t.label}</span>
                    <span className="w-[36px] text-right tabular-nums text-ink2">
                      {fmtCount(t.grads)}
                    </span>
                    <span className="w-[26px] text-right tabular-nums text-ink3">
                      {Math.round((t.grads / Math.max(1, stats.totalGrads)) * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </Block>

            <CrossTab {...stats.crossA} />
            <CrossTab {...stats.crossB} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ---------- private subcomponents ---------- */

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="micro text-ink3">{title}</h3>
      {children}
    </section>
  )
}

function Big({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div
      className="text-[26px] font-semibold leading-none tracking-[-0.03em] tabular-nums text-ink"
      style={style}
    >
      {children}
    </div>
  )
}

function Note({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] leading-none text-ink3">{children}</div>
}

/** A cross-tab: one row per band of the OTHER variable, bar length encoding the
 *  weighted average of the active layer. Color repeats the encoding so the row
 *  reads the same way the map does; the number is always printed beside it, so
 *  color is never the only signal. */
function CrossTab({
  title,
  rows,
}: {
  title: string
  rows: { label: string; value: string; pct: number; fill: string }[]
}) {
  return (
    <Block title={title}>
      <div className="flex flex-col gap-[3px]">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-1.5 text-[11px] leading-none">
            <span className="w-[54px] shrink-0 text-right tabular-nums text-ink3">{r.label}</span>
            <span className="h-[9px] w-[62px] shrink-0 overflow-hidden rounded-[2px] bg-line">
              <span
                className="block h-full rounded-[2px]"
                style={{ width: `${Math.max(2, Math.min(100, r.pct))}%`, background: r.fill }}
              />
            </span>
            <span className="w-[34px] shrink-0 text-right tabular-nums text-ink2">{r.value}</span>
          </div>
        ))}
      </div>
    </Block>
  )
}

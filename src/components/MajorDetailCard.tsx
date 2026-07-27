import { useId, useMemo, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { REDUCED_TWEEN, SPRING, type Mode } from '../design/tokens'
import {
  bandOf,
  exposureBand,
  exposureColor,
  fmtCount,
  fmtExposure,
  fmtPay,
  fmtRatio,
  growthOf,
} from '../design/scales'
import { topOccupations } from '../lib/normalizeMajors'
import type { Major } from '../types'
import DataChip from './DataChip'
import ShareCard from './ShareCard'

// One plain-language line per band — the exposure-≠-job-loss framing in words.
const VERDICT: Record<string, string> = {
  Rewired: 'A lot of the day-to-day is AI-reachable, so the skill mix shifts fast — the field doesn’t vanish.',
  Reshaped: 'Many tasks are AI-reachable, so the skill mix shifts while the field itself holds.',
  'Barely touched': 'Most of the work stays hands-on; AI mostly assists at the edges for now.',
}

export default function MajorDetailCard({ major, mode }: { major: Major; mode: Mode }) {
  const growth = growthOf(major.growth)
  const expC = useMemo(() => exposureColor(mode), [mode])
  const band = exposureBand(major.exposure)
  const [shareOpen, setShareOpen] = useState(false)
  const [whyOpen, setWhyOpen] = useState(false)
  const reduce = useReducedMotion()
  const rationaleId = useId()
  // Selection rule lives in the data layer — see topOccupations for what it drops.
  const occupations = useMemo(() => topOccupations(major.occupations), [major.occupations])
  const anyScored = occupations.some((o) => o.exposure !== null)
  const hasRoi = major.payToDebt != null || major.versatility != null

  return (
    <div className="rounded-card border border-line bg-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-xl font-semibold tracking-tight text-ink">{major.major}</h2>
          <div className="micro mt-1 flex items-center gap-2 text-ink3">
            <span>{major.family}</span>
            <span aria-hidden>·</span>
            <span>CIP {major.cip}</span>
          </div>
        </div>
        <button
          onClick={() => setShareOpen(true)}
          aria-label={`Share ${major.major}`}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-[12px] font-medium text-ink2 transition-colors hover:bg-raised hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
        >
          <svg width="13" height="13" viewBox="0 0 15 15" fill="none" aria-hidden>
            <circle cx="11.5" cy="3" r="1.9" stroke="currentColor" strokeWidth="1.3" />
            <circle cx="3.5" cy="7.5" r="1.9" stroke="currentColor" strokeWidth="1.3" />
            <circle cx="11.5" cy="12" r="1.9" stroke="currentColor" strokeWidth="1.3" />
            <path d="M9.8 4 5.2 6.5M5.2 8.5 9.8 11" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
          Share
        </button>
      </div>

      <Gauge value={major.exposure} mode={mode} />

      {/* ONE score block, not two. The gauge stated the number and a separate
          pill row restated the same reading beside it — two competing score
          displays stacked. Merged: the band now sits directly under the readout
          as part of the gauge's own block (hard rule 2 — the plain-language band
          always accompanies the number, never replaces it), with the verdict as
          its single supporting line. Matches how ShareCard already presents it. */}
      {major.exposure !== null ? (
        <div className="mt-1 text-center">
          <div className="micro text-ink2">{band.label}</div>
          <p className="mx-auto mt-1.5 max-w-[38ch] text-[12.5px] leading-snug text-ink3">
            {VERDICT[band.label]}
          </p>
        </div>
      ) : (
        <div className="mt-3 flex justify-center">
          <DataChip label="Not scored yet" clock />
        </div>
      )}

      <dl className="mt-1 grid grid-cols-3 gap-2">
        <Stat
          label="Median pay"
          value={major.median_pay != null ? fmtPay(major.median_pay) : <DataChip label="No data" />}
        />
        <Stat label="Bachelor's grads" value={fmtCount(major.completions)} />
        <Stat
          label="Job growth"
          value={
            major.growth ? (
              <>
                <span aria-hidden>{growth.glyph} </span>
                {growth.label}
              </>
            ) : (
              <DataChip label="No data" />
            )
          }
          tone={major.growth ? growth.tone?.[mode] : undefined}
        />
      </dl>

      {/* The rationale is the longest text on the card and answers a question most
          readers only ask once, so it sits behind a disclosure instead of pushing
          the occupations below the fold. Collapsed by default; a real <button> with
          aria-expanded so it is keyboard- and screen-reader-navigable. */}
      <div className="mt-4">
        <button
          type="button"
          onClick={() => setWhyOpen((v) => !v)}
          aria-expanded={whyOpen}
          aria-controls={rationaleId}
          className="inline-flex items-center gap-1.5 rounded-md text-[12.5px] font-medium text-ink2 transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
        >
          <svg width="13" height="13" viewBox="0 0 14 14" fill="none" aria-hidden className="shrink-0">
            <circle cx="7" cy="7" r="5.6" stroke="currentColor" strokeWidth="1.3" />
            <path d="M7 6.2v3.4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            <circle cx="7" cy="4.3" r="0.75" fill="currentColor" />
          </svg>
          Why this score?
          <motion.svg
            width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden
            animate={{ rotate: whyOpen ? 180 : 0 }}
            transition={reduce ? REDUCED_TWEEN : { duration: 0.18 }}
            className="shrink-0 text-ink3"
          >
            <path d="M2 4l3 3 3-3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
          </motion.svg>
        </button>

        <AnimatePresence initial={false}>
          {whyOpen && (
            <motion.div
              key="rationale"
              id={rationaleId}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={reduce ? REDUCED_TWEEN : { duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              className="overflow-hidden"
            >
              <div className="mt-2 rounded-lg border border-line bg-raised p-3">
                <p className="text-[12.5px] leading-relaxed text-ink2">{major.rationale}</p>
                {/* The ROI meters live here rather than in the main flow: two
                    full-width bars between the gauge and the occupations flattened
                    the hierarchy, and they answer the same "how did you get here"
                    question the rationale does. */}
                {hasRoi && (
                  <div className="mt-3 space-y-3 border-t border-line pt-3">
                    {major.payToDebt != null && (
                      <Meter
                        label="Pay vs. debt"
                        value={fmtRatio(major.payToDebt)}
                        fill={major.payToDebtRank ?? 0}
                        caption="early-career pay per $1 of typical student debt"
                      />
                    )}
                    {major.versatility != null && (
                      <Meter
                        label="Career versatility"
                        value={bandOf(major.versatility ?? 0)}
                        fill={major.versatilityRank ?? 0}
                        caption={`maps to ${major.versatility} related occupation${major.versatility === 1 ? '' : 's'}`}
                      />
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="mt-5 flex items-baseline justify-between gap-2">
        <h3 className="micro text-ink3">Top occupations</h3>
        {/* Label what the rows actually show. This carried "AI exposure pending"
            while displaying pay and outlook — a caption about a number the section
            doesn't render. Per-occupation exposure isn't in the feed yet; when it
            lands, `anyScored` flips and the bars appear. */}
        {occupations.length > 0 && (
          <span className="micro normal-case tracking-normal text-ink3">
            {anyScored ? 'most exposed first' : 'median pay · projected growth'}
          </span>
        )}
      </div>
      {occupations.length === 0 ? (
        // Same idiom the stats above use for a missing field, so an unmapped major
        // reads as "not scored yet" rather than a section that failed to render.
        <div className="mt-2">
          <DataChip label="No occupations mapped yet" clock />
        </div>
      ) : (
      <ul className="mt-2">
        {occupations.map((o) => (
          <li key={o.soc} className="flex items-center gap-3 border-t border-line py-2.5 first:border-t-0">
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-ink">{o.title}</div>
              <div className="micro flex flex-wrap items-center gap-x-1.5 text-ink3">
                <span>SOC {o.soc}</span>
                {o.medianPay != null && (
                  <>
                    <span aria-hidden>·</span>
                    <span>{fmtPay(o.medianPay)} median</span>
                  </>
                )}
                {o.outlook != null && (
                  <>
                    <span aria-hidden>·</span>
                    <span>{o.outlook > 0 ? '+' : ''}{o.outlook}% outlook</span>
                  </>
                )}
              </div>
            </div>
            {/* Bar and score only when this occupation is actually scored. An empty
                track would read as zero exposure — a claim the data doesn't make. */}
            {o.exposure !== null && (
              <>
                <div className="h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-line" aria-hidden>
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${(o.exposure / 10) * 100}%`, background: expC(o.exposure) }}
                  />
                </div>
                <span
                  className="w-8 shrink-0 text-right text-[13px] font-semibold text-ink"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                  aria-label={`exposure ${fmtExposure(o.exposure)} out of 10`}
                >
                  {fmtExposure(o.exposure)}
                </span>
              </>
            )}
          </li>
        ))}
      </ul>
      )}

      <ShareCard major={major} mode={mode} open={shareOpen} onClose={() => setShareOpen(false)} />
    </div>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: React.ReactNode
  tone?: string
}) {
  return (
    <div className="rounded-lg border border-line bg-raised px-2.5 py-2">
      <dt className="micro text-ink3">{label}</dt>
      <dd
        className="mt-0.5 text-[13.5px] font-semibold"
        style={{ color: tone ?? 'var(--ink)', fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </dd>
    </div>
  )
}

/* A labeled 0–1 meter for non-exposure metrics (pay-to-debt, versatility).
   Neutral ink fill — deliberately NOT the exposure/pay ramps, so it never reads
   as an AI-exposure or pay score. Value text always accompanies the bar. */
function Meter({
  label,
  value,
  fill,
  caption,
}: {
  label: string
  value: string
  fill: number
  caption: string
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="micro text-ink3">{label}</span>
        <span
          className="text-[13px] font-semibold text-ink"
          style={{ fontVariantNumeric: 'tabular-nums' }}
        >
          {value}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-line" aria-hidden>
        <div
          className="h-full rounded-full bg-ink2"
          style={{ width: `${Math.max(0, Math.min(1, fill)) * 100}%` }}
        />
      </div>
      <p className="micro mt-1 normal-case tracking-normal text-ink3">{caption}</p>
    </div>
  )
}

/* 180° exposure gauge: ramp-colored track, spring-animated needle. */
function Gauge({ value, mode }: { value: number | null; mode: Mode }) {
  const reduce = useReducedMotion()
  const spr = reduce ? REDUCED_TWEEN : SPRING
  const expC = exposureColor(mode)

  const cx = 100
  const cy = 92
  const r = 74
  const N = 36

  const pt = (angle: number, radius: number) => ({
    x: cx + radius * Math.cos(angle),
    y: cy - radius * Math.sin(angle),
  })
  const seg = (t0: number, t1: number) => {
    const a0 = Math.PI * (1 - t0)
    const a1 = Math.PI * (1 - t1)
    const p0 = pt(a0, r)
    const p1 = pt(a1, r)
    return `M ${p0.x} ${p0.y} A ${r} ${r} 0 0 1 ${p1.x} ${p1.y}`
  }
  // Unscored: no needle is drawn (see `value === null` below); the readout
  // renders an em dash rather than implying a score.
  const needleAngle = Math.PI * (1 - (value ?? 0) / 10)
  const tipP = pt(needleAngle, r - 26)

  return (
    /* viewBox is taller than the arc needs: the readout sits BELOW the pivot,
       outside the needle's 180° sweep. Centred in the arc it was crossed by the
       needle at mid-range scores — at 6.5 the needle ran through the digits. */
    <svg
      viewBox="0 0 200 150"
      className="mx-auto mt-4 block w-full max-w-[240px]"
      role="img"
      aria-label={`Exposure gauge: ${fmtExposure(value)} out of 10`}
    >
      {Array.from({ length: N }, (_, i) => (
        <path
          key={i}
          d={seg(i / N, (i + 1) / N + 0.004)}
          stroke={expC(((i + 0.5) / N) * 10)}
          strokeWidth={11}
          fill="none"
        />
      ))}
      {value !== null && (
        <motion.line
          x1={cx}
          y1={cy}
          initial={{ x2: cx - (r - 26), y2: cy }}
          animate={{ x2: tipP.x, y2: tipP.y }}
          transition={spr}
          stroke="var(--ink)"
          strokeWidth={2.5}
          strokeLinecap="round"
        />
      )}
      {/* The pivot carries this major's own ramp color — the same expC() the map
          tiles use, so the gauge and the tile read as one metric. Unscored falls
          back to ink3 rather than the ramp's low end. */}
      <circle cx={cx} cy={cy} r={5.5} fill={value === null ? 'var(--ink3)' : expC(value)} />
      <text x={cx - r} y={cy + 12} textAnchor="middle" fill="var(--ink3)" style={{ fontSize: 9.5 }}>
        low
      </text>
      <text x={cx + r} y={cy + 12} textAnchor="middle" fill="var(--ink3)" style={{ fontSize: 9.5 }}>
        high
      </text>
      <text
        x={cx}
        y={cy + 40}
        textAnchor="middle"
        fill="var(--ink)"
        style={{ fontSize: 30, fontWeight: 640, fontVariantNumeric: 'tabular-nums' }}
      >
        {fmtExposure(value)}
      </text>
      <text x={cx} y={cy + 52} textAnchor="middle" fill="var(--ink3)" style={{ fontSize: 10 }}>
        / 10 exposure
      </text>
    </svg>
  )
}

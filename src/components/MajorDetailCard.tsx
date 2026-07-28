import { useId, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { type Mode, EASE } from '../design/tokens'
import {
  exposureColor,
  fmtCount,
  fmtExposure,
  fmtOutlook,
  fmtPay,
  fmtRatio,
  growthOf,
} from '../design/scales'
import type { Major } from '../types'
import DataChip from './DataChip'
import ShareCard from './ShareCard'

export default function MajorDetailCard({ major, mode }: { major: Major; mode: Mode }) {
  const growth = growthOf(major.growth)
  const [shareOpen, setShareOpen] = useState(false)
  const topCareers = major.topCareers ?? []

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

      {/* No band pill — the ring's own color already reads as a band (pale/mint
          = barely touched, deep teal = rewired), and the app-wide "high exposure
          ≠ job loss" framing lives in the pinned caveat banner, so a repeated
          text label here was just saying the same thing a third time. The
          specific, per-major explanation (major.rationale) is one tap away. */}
      {major.exposure !== null ? (
        <div className="mt-2.5 flex items-center justify-center gap-1.5">
          <span className="text-[11.5px] text-ink3">Why this score</span>
          <InfoTip label="Why this exposure score" text={major.rationale} />
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

      {major.payToDebt != null && (
        <div className="mt-4">
          <Meter
            label="Pay vs. debt"
            value={fmtRatio(major.payToDebt)}
            fill={major.payToDebtRank ?? 0}
            caption="early-career pay per $1 of typical student debt"
          />
        </div>
      )}

      {topCareers.length > 0 && (
        <>
          <h3 className="micro mt-5 text-ink3">Top occupations</h3>
          <ul className="mt-2">
            {topCareers.map((c) => (
              <li
                key={c.soc}
                className="flex items-center gap-3 border-t border-line py-2.5 first:border-t-0"
              >
                <span
                  aria-hidden
                  className={
                    c.rank === 1
                      ? 'grid size-4 shrink-0 place-items-center rounded-full bg-ink text-[9px] font-semibold text-surface'
                      : 'w-4 shrink-0 text-center text-[11px] text-ink3'
                  }
                >
                  {c.rank}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-[13px] font-medium text-ink">{c.title}</span>
                    {c.rank === 1 && (
                      <span className="micro shrink-0 rounded border border-line px-1 py-px text-ink3">
                        top match
                      </span>
                    )}
                  </div>
                  <div className="micro mt-0.5 normal-case tracking-normal text-ink3">
                    {fmtPay(c.medianWage)}
                    {c.outlookPct != null && <> · {fmtOutlook(c.outlookPct)} outlook</>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
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

/* A labeled 0–1 meter for non-exposure metrics (pay-to-debt). Neutral ink
   fill — deliberately NOT the exposure/pay ramps, so it never reads as an
   AI-exposure or pay score. Value text always accompanies the bar. */
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

/* Full-circle exposure ring: the ramp itself is the pointer. The track fills
   clockwise from 12 o'clock through the ramp's own pale→deep colors up to the
   value's position, then flat `--line` gray for the remainder — so the fill's
   own hue still answers "how far into the range is this" without a needle,
   which is what let the old 180° gauge waste its bottom half as empty margin. */
function Gauge({ value, mode }: { value: number | null; mode: Mode }) {
  const expC = exposureColor(mode)

  const cx = 100
  const cy = 100
  const r = 78
  const sw = 14
  const N = 48
  const f = value === null ? 0 : Math.max(0, Math.min(1, value / 10))
  const segCount = f > 0 ? Math.max(1, Math.round(N * f)) : 0

  const polar = (angleDeg: number) => {
    const a = ((angleDeg - 90) * Math.PI) / 180
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
  }
  const arc = (a0: number, a1: number) => {
    const p0 = polar(a0)
    const p1 = polar(a1)
    const large = a1 - a0 > 180 ? 1 : 0
    return `M ${p0.x} ${p0.y} A ${r} ${r} 0 ${large} 1 ${p1.x} ${p1.y}`
  }

  return (
    <svg
      viewBox="0 0 200 200"
      className="mx-auto mt-4 block w-full max-w-[200px]"
      role="img"
      aria-label={`Exposure gauge: ${fmtExposure(value)} out of 10`}
    >
      <path d={arc(0, 359.999)} stroke="var(--line)" strokeWidth={sw} fill="none" />
      {Array.from({ length: segCount }, (_, i) => {
        const t0 = i / N
        const t1 = Math.min((i + 1) / N + 0.006, f)
        const isEnd = i === 0 || i === segCount - 1
        return (
          <path
            key={i}
            d={arc(t0 * 360, t1 * 360)}
            stroke={expC(t0 * 10)}
            strokeWidth={sw}
            strokeLinecap={isEnd ? 'round' : 'butt'}
            fill="none"
          />
        )
      })}
      <text
        x={cx}
        y={cy - 4}
        textAnchor="middle"
        fill="var(--ink)"
        style={{ fontSize: 34, fontWeight: 640, fontVariantNumeric: 'tabular-nums' }}
      >
        {fmtExposure(value)}
      </text>
      <text x={cx} y={cy + 19} textAnchor="middle" fill="var(--ink3)" style={{ fontSize: 12 }}>
        / 10 exposure
      </text>
    </svg>
  )
}

/* Hoverable/focusable (i) — same visual language as the app-wide exposure
   caveat button (Explore.tsx), just sized for an inline pill. Glass is a
   legitimate surface here (CLAUDE.md hard rule 5: floating context only) since
   this genuinely floats over the card rather than sitting in the data flow. */
function InfoTip({ label, text }: { label: string; text: string }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label={label}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((v) => !v)}
        className="grid size-4 shrink-0 place-items-center rounded-full border border-line text-[9px] font-semibold text-ink3 transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 focus-visible:ring-offset-surface"
      >
        i
      </button>
      <AnimatePresence>
        {open && (
          <motion.span
            id={id}
            role="tooltip"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15, ease: EASE }}
            className="glass pointer-events-none absolute left-1/2 top-6 z-20 w-64 -translate-x-1/2 rounded-card p-3 text-[12px] leading-relaxed text-ink2 shadow-xl"
          >
            {text}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  )
}

import { useMemo } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { REDUCED_TWEEN, SPRING, type Mode } from '../design/tokens'
import { bandOf, exposureColor, fmtCount, fmtExposure, fmtPay, fmtRatio, growthOf } from '../design/scales'
import type { Major } from '../types'

export default function MajorDetailCard({ major, mode }: { major: Major; mode: Mode }) {
  const growth = growthOf(major.growth)
  const expC = useMemo(() => exposureColor(mode), [mode])
  // "99-9999 / NO MATCH" is the source's placeholder for unmapped employment.
  const occupations = major.occupations.filter((o) => o.soc !== '99-9999')
  const hasRoi = major.payToDebt != null || major.versatility != null

  return (
    <div className="rounded-card border border-line bg-surface p-5">
      <h2 className="text-xl font-semibold tracking-tight text-ink">{major.major}</h2>
      <div className="micro mt-1 flex items-center gap-2 text-ink3">
        <span>{major.family}</span>
        <span aria-hidden>·</span>
        <span>CIP {major.cip}</span>
      </div>

      <Gauge value={major.exposure} mode={mode} />

      <dl className="mt-1 grid grid-cols-3 gap-2">
        <Stat label="Median pay" value={fmtPay(major.median_pay)} />
        <Stat label="Bachelor's grads" value={fmtCount(major.completions)} />
        <Stat
          label="Job growth"
          value={
            <>
              <span aria-hidden>{growth.glyph} </span>
              {growth.label}
            </>
          }
          tone={growth.tone?.[mode]}
        />
      </dl>

      {hasRoi && (
        <div className="mt-4 space-y-3">
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

      <p className="mt-4 text-[13px] leading-relaxed text-ink2">{major.rationale}</p>

      <h3 className="micro mt-5 text-ink3">Mapped occupations</h3>
      <ul className="mt-2">
        {occupations.map((o) => (
          <li key={o.soc} className="flex items-center gap-3 border-t border-line py-2.5 first:border-t-0">
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-medium text-ink">{o.title}</div>
              <div className="micro text-ink3">SOC {o.soc}</div>
            </div>
            <div className="h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-line" aria-hidden>
              <div
                className="h-full rounded-full"
                style={{ width: `${((o.exposure ?? 0) / 10) * 100}%`, background: expC(o.exposure) }}
              />
            </div>
            <span
              className="w-8 shrink-0 text-right text-[13px] font-semibold text-ink"
              style={{ fontVariantNumeric: 'tabular-nums' }}
              aria-label={`exposure ${fmtExposure(o.exposure)} out of 10`}
            >
              {fmtExposure(o.exposure)}
            </span>
          </li>
        ))}
      </ul>
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
    <svg
      viewBox="0 0 200 106"
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
      <circle cx={cx} cy={cy} r={4.5} fill="var(--ink)" />
      <text
        x={cx}
        y={cy - 22}
        textAnchor="middle"
        fill="var(--ink)"
        style={{ fontSize: 27, fontWeight: 640, fontVariantNumeric: 'tabular-nums' }}
      >
        {fmtExposure(value)}
      </text>
      <text x={cx} y={cy - 8} textAnchor="middle" fill="var(--ink3)" style={{ fontSize: 10 }}>
        / 10 exposure
      </text>
      <text x={cx - r} y={cy + 12} textAnchor="middle" fill="var(--ink3)" style={{ fontSize: 9.5 }}>
        low
      </text>
      <text x={cx + r} y={cy + 12} textAnchor="middle" fill="var(--ink3)" style={{ fontSize: 9.5 }}>
        high
      </text>
    </svg>
  )
}

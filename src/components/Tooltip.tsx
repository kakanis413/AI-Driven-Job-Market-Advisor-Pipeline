import { AnimatePresence, motion } from 'framer-motion'
import { exposureColor, fmtCount, fmtExposure, fmtPay, growthOf } from '../design/scales'
import type { Mode } from '../design/tokens'
import type { TipData } from '../types'

const W = 300
const H = 216

export default function Tooltip({ tip, mode }: { tip: TipData | null; mode: Mode }) {
  let left = 0
  let top = 0
  if (tip) {
    left = tip.x + 16
    if (left + W > window.innerWidth - 8) left = Math.max(8, tip.x - W - 16)
    top = tip.y + 18
    if (top + H > window.innerHeight - 72) top = Math.max(8, tip.y - H - 12)
  }
  const growth = tip && growthOf(tip.major.growth)
  return (
    <AnimatePresence>
      {tip && growth && (
        <motion.div
          key="tooltip"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 4 }}
          transition={{ duration: 0.15, ease: [0.22, 1, 0.36, 1] }}
          className="glass pointer-events-none fixed z-50 rounded-card p-4 shadow-xl"
          style={{ left, top, width: W }}
          role="status"
        >
          <div className="flex items-start justify-between gap-3">
            <span className="text-sm font-semibold leading-tight text-ink">{tip.major.major}</span>
            <span className="micro mt-0.5 shrink-0 text-ink3">{tip.major.family}</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5">
            <Metric label="AI exposure">
              <span
                aria-hidden
                className="mr-1.5 inline-block size-2.5 rounded-full align-[-1px]"
                style={{ background: exposureColor(mode)(tip.major.exposure) }}
              />
              <b style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtExposure(tip.major.exposure)}</b>
              <span className="text-ink3"> /10</span>
            </Metric>
            <Metric label="Median pay">
              <b style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtPay(tip.major.median_pay)}</b>
            </Metric>
            <Metric label="Bachelor's grads / yr">
              <b style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtCount(tip.major.completions)}</b>
            </Metric>
            <Metric label="Job growth">
              <span aria-hidden>{growth.glyph} </span>
              <b>{growth.label}</b>
            </Metric>
          </div>
          <p className="mt-3 border-t border-line pt-3 text-[12.5px] leading-relaxed text-ink2">
            {tip.major.rationale}
          </p>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="micro text-ink3">{label}</div>
      <div className="mt-0.5 text-[13px] text-ink">{children}</div>
    </div>
  )
}

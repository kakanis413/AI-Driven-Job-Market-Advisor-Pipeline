import { AnimatePresence, motion } from 'framer-motion'
import { exposureColor, exposureRampDomain, fmtExposure, fmtPay, payColor } from '../design/scales'
import type { Layer, Mode } from '../design/tokens'

const SEGMENTS = 28

export default function Legend({
  layer,
  mode,
  payExtent,
  compact = false,
}: {
  layer: Layer
  mode: Mode
  payExtent: [number, number]
  /** Horizontal, condensed row for the toolbar below xl, where the vertical
   *  inline legend doesn't fit. Same encoding, less chrome. */
  compact?: boolean
}) {
  // The exposure ramp is fitted to the observed range, not to 0–10, so the bar
  // is swept across THAT domain and labelled with its real endpoints. Printing
  // "0" and "10" here would key the map to colors it never paints.
  const [expLo, expHi] = exposureRampDomain()
  const scale =
    layer === 'exposure'
      ? (t: number) => exposureColor(mode)(expLo + t * (expHi - expLo))
      : (t: number) => payColor(mode, payExtent)(payExtent[0] + t * (payExtent[1] - payExtent[0]))

  const title = layer === 'exposure' ? 'AI exposure /10' : 'Median pay'
  const lo = layer === 'exposure' ? fmtExposure(expLo) : fmtPay(payExtent[0])
  const hi = layer === 'exposure' ? fmtExposure(expHi) : fmtPay(payExtent[1])
  // Hue-neutral: describes the ramp by depth (pale → deep), not by a specific
  // color name, so it stays accurate whichever ramp ships.
  const ariaLabel =
    layer === 'exposure'
      ? `Legend: AI exposure color scale, pale at ${fmtExposure(expLo)} (lowest scored) to deep at ${fmtExposure(expHi)} (highest scored), on a 0 to 10 scale`
      : `Legend: median-pay color scale, pale at ${fmtPay(payExtent[0])} to deep at ${fmtPay(payExtent[1])}`

  const bar = (
    <div
      className={`flex h-2 overflow-hidden rounded-full ${compact ? 'w-24 sm:w-28' : 'w-44 md:w-56'}`}
    >
      {Array.from({ length: SEGMENTS }, (_, i) => (
        <div key={i} className="h-full flex-1" style={{ background: scale(i / (SEGMENTS - 1)) }} />
      ))}
    </div>
  )

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={`${layer}-${mode}-${compact ? 'c' : 'f'}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.25 }}
        role="img"
        aria-label={ariaLabel}
        className={compact ? 'flex items-center gap-2' : 'flex flex-col gap-1.5'}
      >
        {/* Every label here rides the one `micro` token — title, endpoint
            captions, and the area note all render at the same size/tracking as
            the toolbar labels and column headers. */}
        {compact ? (
          <>
            <span className="micro shrink-0 text-ink3">{title}</span>
            <span className="micro shrink-0 text-ink3" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {lo}
            </span>
            {bar}
            <span className="micro shrink-0 text-ink3" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {hi}
            </span>
          </>
        ) : (
          <>
            <div className="micro text-ink3">{title}</div>
            {bar}
            <div
              className="micro flex justify-between text-ink3"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              <span>{layer === 'exposure' ? `${fmtExposure(expLo)} · low` : fmtPay(payExtent[0])}</span>
              <span>{layer === 'exposure' ? `${fmtExposure(expHi)} · high` : fmtPay(payExtent[1])}</span>
            </div>
            {/* The other half of the encoding: color is exposure/pay, area is size. */}
            <div className="micro text-ink3">Tile area ≈ grads · small majors sized up</div>
          </>
        )}
      </motion.div>
    </AnimatePresence>
  )
}

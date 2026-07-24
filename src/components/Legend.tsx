import { AnimatePresence, motion } from 'framer-motion'
import { exposureColor, fmtPay, payColor } from '../design/scales'
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
  const scale =
    layer === 'exposure'
      ? (t: number) => exposureColor(mode)(t * 10)
      : (t: number) => payColor(mode, payExtent)(payExtent[0] + t * (payExtent[1] - payExtent[0]))

  const title = layer === 'exposure' ? 'AI exposure /10' : 'Median pay'
  const lo = layer === 'exposure' ? '0' : fmtPay(payExtent[0])
  const hi = layer === 'exposure' ? '10' : fmtPay(payExtent[1])
  // Hue-neutral: describes the ramp by depth (pale → deep), not by a specific
  // color name, so it stays accurate whichever ramp ships.
  const ariaLabel =
    layer === 'exposure'
      ? 'Legend: AI exposure color scale, pale at 0 (low) to deep at 10 (high)'
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
              <span>{layer === 'exposure' ? '0 · low' : fmtPay(payExtent[0])}</span>
              <span>{layer === 'exposure' ? '10 · high' : fmtPay(payExtent[1])}</span>
            </div>
            {/* The other half of the encoding: color is exposure/pay, area is size. */}
            <div className="micro text-ink3">Tile area ≈ grads · small majors sized up</div>
          </>
        )}
      </motion.div>
    </AnimatePresence>
  )
}

import { AnimatePresence, motion } from 'framer-motion'
import { exposureColor, fmtPay, payColor } from '../design/scales'
import type { Layer, Mode } from '../design/tokens'

const SEGMENTS = 28

export default function Legend({
  layer,
  mode,
  payExtent,
}: {
  layer: Layer
  mode: Mode
  payExtent: [number, number]
}) {
  const scale =
    layer === 'exposure'
      ? (t: number) => exposureColor(mode)(t * 10)
      : (t: number) => payColor(mode, payExtent)(payExtent[0] + t * (payExtent[1] - payExtent[0]))

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={`${layer}-${mode}`}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.25 }}
        className="flex flex-col gap-1.5"
        role="img"
        aria-label={
          layer === 'exposure'
            ? 'Legend: color scale from pale violet at exposure 0 to deep violet at exposure 10'
            : `Legend: color scale from light blue at ${fmtPay(payExtent[0])} to dark blue at ${fmtPay(payExtent[1])}`
        }
      >
        <div className="micro text-ink3">{layer === 'exposure' ? 'AI exposure /10' : 'Median pay'}</div>
        <div className="flex h-2 w-44 overflow-hidden rounded-full md:w-56">
          {Array.from({ length: SEGMENTS }, (_, i) => (
            <div key={i} className="h-full flex-1" style={{ background: scale(i / (SEGMENTS - 1)) }} />
          ))}
        </div>
        <div className="flex justify-between text-[11px] text-ink3" style={{ fontVariantNumeric: 'tabular-nums' }}>
          <span>{layer === 'exposure' ? '0 · low' : fmtPay(payExtent[0])}</span>
          <span>{layer === 'exposure' ? '10 · high' : fmtPay(payExtent[1])}</span>
        </div>
        {/* The other half of the encoding: color is exposure/pay, area is size. */}
        <div className="micro text-ink3">Tile area = bachelor's grads</div>
      </motion.div>
    </AnimatePresence>
  )
}

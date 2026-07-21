import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { REDUCED_TWEEN, SPRING, type Layer, type Mode } from '../design/tokens'
import {
  exposureColor,
  fmtCount,
  fmtExposure,
  fmtPay,
  NULL_FILL,
  inkFor,
  normalize,
  payColor,
  shade,
} from '../design/scales'
import { layoutTreemap, type Rect, type Tile } from '../lib/layout'
import type { Major, TipData } from '../types'

interface Props {
  majors: Major[]
  width: number
  height: number
  mode: Mode
  layer: Layer
  payExtent: [number, number]
  query: string
  selectedCip: string | null
  onSelect: (cip: string) => void
  onTip: (tip: TipData | null) => void
  /** Last-known tile geometry, shared with HeatmapGrid for cross-view morphs. */
  geomRef: { current: Map<string, Rect> }
}

export default memo(function Treemap({
  majors,
  width,
  height,
  mode,
  layer,
  payExtent,
  query,
  selectedCip,
  onSelect,
  onTip,
  geomRef,
}: Props) {
  const reduce = useReducedMotion()
  const spr = reduce ? REDUCED_TWEEN : SPRING

  const { tiles, bands } = useMemo(
    () => layoutTreemap(majors, width, height, selectedCip),
    [majors, width, height, selectedCip],
  )

  // Snapshot of the other view's geometry at mount — tiles morph in from it.
  const entryGeom = useRef<Map<string, Rect> | null>(null)
  if (entryGeom.current === null) entryGeom.current = new Map(geomRef.current)
  const fromMorph = entryGeom.current.size > 0

  useEffect(() => {
    const m = geomRef.current
    m.clear()
    for (const t of tiles) m.set(t.major.cip, { x: t.x, y: t.y, w: t.w, h: t.h })
  }, [tiles, geomRef])

  // Load-reveal stagger, ordered by area (biggest first), disabled after mount.
  const [revealed, setRevealed] = useState(fromMorph)
  useEffect(() => {
    const t = setTimeout(() => setRevealed(true), 750)
    return () => clearTimeout(t)
  }, [])
  const revealOrder = useMemo(() => {
    const sorted = [...tiles].sort((a, b) => b.w * b.h - a.w * a.h)
    return new Map(sorted.map((t, i) => [t.major.cip, i]))
  }, [tiles])

  const q = normalize(query)
  const matches = (m: Major) =>
    normalize(m.major).includes(q) || normalize(m.family).includes(q)

  const expC = useMemo(() => exposureColor(mode), [mode])
  const payC = useMemo(() => payColor(mode, payExtent), [mode, payExtent])

  const gRefs = useRef<(SVGGElement | null)[]>([])
  const focusTile = (i: number) => gRefs.current[i]?.focus()

  return (
    <svg
      width={width}
      height={height}
      role="group"
      aria-label={`Treemap of ${tiles.length} college majors, sized by graduates and colored by ${
        layer === 'exposure' ? 'AI exposure' : 'median pay'
      }`}
    >
      {bands.map(
        (b) =>
          b.w > 70 && (
            <motion.text
              key={b.family}
              initial={false}
              animate={{ x: b.x + 2, y: b.y + 15 }}
              transition={spr}
              fill="var(--ink3)"
              style={{ fontSize: 10.5, fontWeight: 580, letterSpacing: '0.08em' }}
            >
              {b.family.toUpperCase()}
            </motion.text>
          ),
      )}
      {tiles.map((t, i) => {
        let dim = 1
        if (q && !matches(t.major)) dim = 0.18
        if (selectedCip && t.major.cip !== selectedCip) dim = Math.min(dim, 0.35)
        return (
          <TileView
            key={t.major.cip}
            t={t}
            index={i}
            spr={spr}
            layer={layer}
            mode={mode}
            fill={
              layer === 'exposure'
                ? expC(t.major.exposure)
                : t.major.median_pay != null
                  ? payC(t.major.median_pay)
                  : NULL_FILL[mode]
            }
            dim={dim}
            selected={t.major.cip === selectedCip}
            entry={entryGeom.current!.get(t.major.cip)}
            delay={
              revealed ? 0 : Math.min((revealOrder.get(t.major.cip) ?? 0) * 0.014, 0.45)
            }
            onSelect={onSelect}
            onTip={onTip}
            refCb={(el) => (gRefs.current[i] = el)}
            onArrow={(dir) => focusTile(i + dir)}
          />
        )
      })}
    </svg>
  )
})

function TileView({
  t,
  spr,
  layer,
  mode,
  fill,
  dim,
  selected,
  entry,
  delay,
  onSelect,
  onTip,
  refCb,
  onArrow,
}: {
  t: Tile
  index: number
  spr: object
  layer: Layer
  mode: Mode
  fill: string
  dim: number
  selected: boolean
  entry: Rect | undefined
  delay: number
  onSelect: (cip: string) => void
  onTip: (tip: TipData | null) => void
  refCb: (el: SVGGElement | null) => void
  onArrow: (dir: 1 | -1) => void
}) {
  const [hover, setHover] = useState(false)
  const [focus, setFocus] = useState(false)
  const m = t.major
  const ink = inkFor(fill)
  const showName = t.w > 78 && t.h > 46
  // Below the name threshold a tile renders NOTHING — no name, no number.
  // A repeated "5.0" or a truncated acronym is noise that looks broken; at this
  // scale color is the only encoding that works and the detail is in the
  // tooltip. Hard rule 2 (color paired with a number) is still met wherever a
  // label fits, and everywhere via the tooltip on hover/focus.
  const value = layer === 'exposure' ? fmtExposure(m.exposure) : fmtPay(m.median_pay)
  const maxChars = Math.max(3, Math.floor((t.w - 14) / 6.6))
  const label = m.major.length > maxChars ? `${m.major.slice(0, maxChars - 1)}…` : m.major

  const transition = { ...spr, delay, opacity: { duration: 0.25, delay } }

  return (
    <motion.g
      ref={refCb}
      className="cursor-pointer focus:outline-none"
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`${m.major}: AI exposure ${fmtExposure(m.exposure)} out of 10, median pay ${fmtPay(
        m.median_pay,
      )}, ${fmtCount(m.completions)} graduates per year. Press Enter for details.`}
      initial={
        entry
          ? { x: entry.x, y: entry.y, opacity: 1, scale: 1 }
          : { x: t.x, y: t.y, opacity: 0, scale: 0.94 }
      }
      animate={{ x: t.x, y: t.y, opacity: dim, scale: 1 }}
      transition={transition}
      onClick={() => onSelect(m.cip)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect(m.cip)
        } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
          e.preventDefault()
          onArrow(1)
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
          e.preventDefault()
          onArrow(-1)
        }
      }}
      onPointerMove={(e) => {
        setHover(true)
        onTip({ major: m, x: e.clientX, y: e.clientY })
      }}
      onPointerLeave={() => {
        setHover(false)
        onTip(null)
      }}
      onFocus={(e) => {
        // Only keyboard focus gets the accent ring + tooltip; pointer clicks
        // rely on the selection ring in the tile's own color.
        const el = e.currentTarget as SVGGElement
        if (!el.matches(':focus-visible')) return
        setFocus(true)
        const r = el.getBoundingClientRect()
        onTip({ major: m, x: r.right, y: r.top })
      }}
      onBlur={() => {
        setFocus(false)
        onTip(null)
      }}
    >
      <motion.rect
        rx={4}
        initial={entry ? { width: entry.w, height: entry.h, fill } : { width: t.w, height: t.h, fill }}
        animate={{ width: t.w, height: t.h, fill }}
        transition={{ ...spr, delay, fill: { duration: 0.4, ease: [0.22, 1, 0.36, 1] } }}
        stroke="var(--surface)"
        strokeWidth={1.5}
      />
      {showName && (
        <text x={9} y={19} fill={ink} style={{ fontSize: 12.5, fontWeight: 600 }}>
          {label}
        </text>
      )}
      {showName && (
        <text
          x={9}
          y={35}
          fill={ink}
          fillOpacity={0.82}
          style={{ fontSize: 11, fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}
        >
          {value}
        </text>
      )}
      {(hover || focus || selected) && (
        <motion.rect
          x={1}
          y={1}
          initial={false}
          animate={{ width: Math.max(0, t.w - 2), height: Math.max(0, t.h - 2) }}
          transition={spr}
          rx={4}
          fill="none"
          stroke={focus ? 'var(--accent)' : selected ? shade(fill, mode) : ink}
          strokeOpacity={focus || selected ? 1 : 0.55}
          strokeWidth={2}
          pointerEvents="none"
        />
      )}
    </motion.g>
  )
}

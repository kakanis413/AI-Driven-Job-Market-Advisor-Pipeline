import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import {
  FAMILY_ORDER,
  REDUCED_TWEEN,
  SPRING,
  TABLE_HEAD_H,
  TABLE_ROW_H,
  type Layer,
  type Mode,
} from '../design/tokens'
import {
  NULL_FILL,
  exposureColor,
  growthOf,
  fmtCount,
  fmtExposure,
  fmtPay,
  inkFor,
  payColor,
} from '../design/scales'
import SortMenu from './SortMenu'
import type { Rect } from '../lib/layout'
import type { Family, Major, TipData } from '../types'

const ROW_H = TABLE_ROW_H
const HEAD_H = TABLE_HEAD_H
const GAP = 6

type ColKey = 'exposure' | 'pay' | 'completions' | 'growth'
type SortKey = 'major' | ColKey

interface Col {
  key: ColKey
  label: string
  x: number
  w: number
}

const GROWTH_RANK = { declining: 0, slower: 1, average: 2, faster: 3 } as const

/** Every column the table can show, with the width weight it takes when
 *  visible. Hiding one redistributes its share across the rest. */
const ALL_COLS: [ColKey, string, number][] = [
  ['exposure', 'AI exposure', 1.25],
  ['pay', 'Median pay', 1],
  ['completions', "Bachelor's grads / yr", 1],
  ['growth', 'Job growth', 0.8],
]

interface Props {
  majors: Major[]
  width: number
  /** Max height of the scroll container — the sort bar sticks to its top. */
  height: number
  mode: Mode
  layer: Layer
  payExtent: [number, number]
  selectedCip: string | null
  onSelect: (cip: string) => void
  onTip: (tip: TipData | null) => void
  geomRef: { current: Map<string, Rect> }
}

export default memo(function HeatmapGrid({
  majors,
  width,
  height,
  mode,
  layer,
  payExtent,
  selectedCip,
  onSelect,
  onTip,
  geomRef,
}: Props) {
  const reduce = useReducedMotion()
  const spr = reduce ? REDUCED_TWEEN : SPRING

  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'exposure', dir: -1 })
  const allFamilies = useMemo(
    () => FAMILY_ORDER.filter((f) => majors.some((m) => m.family === f)),
    [majors],
  )
  const [fams, setFams] = useState<Set<Family>>(() => new Set(allFamilies))
  const [hoverRow, setHoverRow] = useState<number | null>(null)
  const [hoverCol, setHoverCol] = useState<ColKey | null>(null)

  // Snapshot of treemap geometry at mount — hero cells morph in from it.
  const entryGeom = useRef<Map<string, Rect> | null>(null)
  if (entryGeom.current === null) entryGeom.current = new Map(geomRef.current)

  const [revealed, setRevealed] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setRevealed(true), 700)
    return () => clearTimeout(t)
  }, [])

  const labelW = Math.min(230, Math.max(150, width * 0.26))
  const bodyW = Math.max(width, labelW + 470)
  const hasGrowth = useMemo(() => majors.some((m) => m.growth), [majors])
  // Columns the data can support (growth only when the source has projections).
  const available = useMemo(
    () => ALL_COLS.filter(([k]) => k !== 'growth' || hasGrowth),
    [hasGrowth],
  )

  const cols = useMemo<Col[]>(() => {
    const total = available.reduce((s, [, , w]) => s + w, 0)
    const space = bodyW - labelW
    let x = labelW
    return available.map(([key, label, wt]) => {
      const w = (space * wt) / total
      const col = { key, label, x, w }
      x += w
      return col
    })
  }, [bodyW, labelW, available])

  const rows = useMemo(() => {
    const filtered = majors.filter((m) => fams.has(m.family))
    const dir = sort.dir
    const val = (m: Major): number | string =>
      sort.key === 'major'
        ? m.major
        : sort.key === 'exposure'
          ? (m.exposure ?? -1) // unscored sorts to the end, like unknown pay
          : sort.key === 'pay'
            ? (m.median_pay ?? -1)
            : sort.key === 'completions'
              ? m.completions
              : m.growth
                ? GROWTH_RANK[m.growth]
                : -1
    const sorted = [...filtered].sort((a, b) => {
      const [va, vb] = [val(a), val(b)]
      const c = typeof va === 'string' ? va.localeCompare(vb as string) : va - (vb as number)
      return c * dir
    })
    // `y` is relative to the BODY container, which sits below the sticky sort
    // bar — so it no longer carries the HEAD_H offset itself.
    return sorted.map((m, i) => ({ m, y: i * ROW_H }))
  }, [majors, fams, sort])

  const heroKey: ColKey = layer === 'pay' ? 'pay' : 'exposure'
  const heroCol = cols.find((c) => c.key === heroKey)!

  useEffect(() => {
    const g = geomRef.current
    g.clear()
    // Stored in the view's own space (header included), so a cross-view morph
    // lands where the cell actually appears on screen.
    for (const { m, y } of rows)
      g.set(m.cip, { x: heroCol.x, y: HEAD_H + y + 4, w: heroCol.w - GAP, h: ROW_H - 8 })
  }, [rows, heroCol, geomRef])

  const expC = useMemo(() => exposureColor(mode), [mode])
  const payC = useMemo(() => payColor(mode, payExtent), [mode, payExtent])
  const maxCompletions = useMemo(
    () => Math.max(...majors.map((m) => m.completions), 1),
    [majors],
  )

  // Sorting lives in the toolbar's SortMenu, which states the field and
  // direction in words — so the headers stay quiet labels with no carets.
  const sortOptions = useMemo(
    () => [
      { key: 'major', label: 'Major', text: true },
      ...available.map(([key, label]) => ({ key, label })),
    ],
    [available],
  )

  const selIdx = rows.findIndex((r) => r.m.cip === selectedCip)
  const bodyH = rows.length * ROW_H
  // Entry geometry comes from the other view's space (header included); the body
  // container starts below the sort bar, so shift it back into body space.
  const entryOf = (cip: string): Rect | undefined => {
    const e = entryGeom.current!.get(cip)
    return e && { ...e, y: e.y - HEAD_H }
  }

  const cellText = (m: Major, key: ColKey): string =>
    key === 'exposure'
      ? fmtExposure(m.exposure)
      : key === 'pay'
        ? fmtPay(m.median_pay)
        : key === 'completions'
          ? fmtCount(m.completions)
          : growthOf(m.growth).label

  return (
    <div className="w-full">
      {/* Toolbar: the sort control, then the family filter chips. When every
          family is on, nothing is actually narrowed, so all chips read as quiet
          outlines instead of eight solid pills fighting the data. The filled
          emphasis only appears once the user narrows to a subset; `aria-pressed`
          always tracks real membership regardless of styling. */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <SortMenu
          options={sortOptions}
          sortKey={sort.key}
          dir={sort.dir}
          onChange={(key, dir) => setSort({ key: key as SortKey, dir })}
        />
        <span aria-hidden className="mx-1 h-5 w-px shrink-0 bg-line" />
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by family">
          {allFamilies.map((f) => {
            const on = fams.has(f)
            const filled = on && fams.size !== allFamilies.length
            return (
              <button
                key={f}
                aria-pressed={on}
                onClick={() =>
                  setFams((prev) => {
                    const next = new Set(prev)
                    if (next.has(f)) next.delete(f)
                    else next.add(f)
                    return next
                  })
                }
                className={`micro h-8 rounded-full border px-3 transition-colors ${
                  filled
                    ? 'border-transparent bg-ink text-page'
                    : 'border-line bg-surface text-ink3 hover:text-ink'
                }`}
              >
                {f}
              </button>
            )
          })}
          {fams.size < allFamilies.length && (
            <button
              onClick={() => setFams(new Set(allFamilies))}
              className="micro h-8 rounded-full px-2 text-accent hover:underline"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      <div
        className="overflow-auto"
        style={{ maxHeight: height }}
        onPointerLeave={() => {
          setHoverRow(null)
          setHoverCol(null)
          onTip(null)
        }}
      >
        {/* Sticky header: quiet column labels, pinned to the top of the scroll
            container with a hairline under it. Sorting is the toolbar's job, so
            these carry no carets — the sorted column just reads in text-ink. */}
        <div
          className="sticky top-0 z-20 border-b border-line bg-page/95 backdrop-blur"
          style={{ width: bodyW, height: HEAD_H }}
        >
          <div className="relative h-full">
            <ColHeader
              label="Major"
              active={sort.key === 'major'}
              style={{ left: 0, width: labelW - GAP }}
            />
            {cols.map((c) => (
              <ColHeader
                key={c.key}
                label={c.label}
                active={sort.key === c.key || hoverCol === c.key}
                style={{ left: c.x, width: c.w - GAP }}
              />
            ))}
          </div>
        </div>

        <div className="relative" style={{ width: bodyW, height: bodyH }}>
          {/* crosshair: one row wash + one column wash that travel */}
          {hoverRow !== null && rows[hoverRow] && (
            <motion.div
              className="pointer-events-none absolute left-0 rounded-lg"
              style={{
                width: bodyW,
                height: ROW_H - 2,
                background: 'color-mix(in srgb, var(--ink) 5%, transparent)',
              }}
              initial={false}
              animate={{ y: hoverRow * ROW_H + 1 }}
              transition={spr}
            />
          )}
          {hoverCol !== null && (
            <motion.div
              className="pointer-events-none absolute rounded-lg"
              style={{
                top: 0,
                width: (cols.find((c) => c.key === hoverCol)?.w ?? 0) - GAP,
                height: bodyH,
                background: 'color-mix(in srgb, var(--ink) 3%, transparent)',
              }}
              initial={false}
              animate={{ x: cols.find((c) => c.key === hoverCol)?.x ?? 0 }}
              transition={spr}
            />
          )}

          {/* spotlight ring on the selected row */}
          {selIdx >= 0 && (
            <motion.div
              className="pointer-events-none absolute left-0 z-10 rounded-[10px] border-2"
              style={{ width: bodyW, borderColor: 'color-mix(in srgb, var(--ink) 45%, transparent)' }}
              initial={false}
              animate={{ y: selIdx * ROW_H, height: ROW_H }}
              transition={spr}
            />
          )}

          <AnimatePresence>
            {rows.flatMap(({ m, y }, i) => {
              const delay = revealed ? 0 : Math.min(i * 0.022, 0.4)
              const hoverProps = (key: ColKey | null) => ({
                onPointerMove: (e: React.PointerEvent) => {
                  // Touch taps fire a synthetic pointermove; skip it so the
                  // hover tooltip/crosshair never flash on touch — those users
                  // get the tap preview sheet instead.
                  if (e.pointerType === 'touch') return
                  setHoverRow(i)
                  setHoverCol(key)
                  onTip({ major: m, x: e.clientX, y: e.clientY })
                },
              })
              const base = {
                exit: { opacity: 0, scale: 0.96, transition: { duration: 0.18 } },
                transition: { ...spr, delay, opacity: { duration: 0.25, delay } },
              }
              const els = [
                <motion.button
                  key={`${m.cip}:label`}
                  {...base}
                  {...hoverProps(null)}
                  initial={{ opacity: 0, y: y + 14 }}
                  animate={{ opacity: 1, y: y + 4, x: 0 }}
                  onClick={() => onSelect(m.cip)}
                  className="absolute flex flex-col justify-center rounded-lg px-2 text-left hover:bg-raised"
                  style={{ width: labelW - GAP, height: ROW_H - 8 }}
                  aria-label={`${m.major}: AI exposure ${fmtExposure(m.exposure)} out of 10, median pay ${fmtPay(m.median_pay)}. Press Enter for details.`}
                >
                  <span className="w-full truncate text-[13px] font-medium leading-tight text-ink">
                    {m.major}
                  </span>
                  <span className="micro text-ink3">{m.family}</span>
                </motion.button>,
              ]
              for (const c of cols) {
                const isHero = c.key === heroCol?.key
                const entry = isHero ? entryOf(m.cip) : undefined
                const fill =
                  c.key === 'exposure'
                    ? expC(m.exposure)
                    : c.key === 'pay'
                      ? m.median_pay != null
                        ? payC(m.median_pay)
                        : NULL_FILL[mode]
                      : undefined
                const wash =
                  c.key === 'completions'
                    ? `color-mix(in srgb, var(--ink) ${Math.round(
                        5 + 33 * Math.sqrt(m.completions / maxCompletions),
                      )}%, transparent)`
                    : undefined
                const tone = c.key === 'growth' ? growthOf(m.growth).tone?.[mode] : undefined
                els.push(
                  <motion.div
                    key={`${m.cip}:${c.key}`}
                    {...base}
                    {...hoverProps(c.key)}
                    initial={
                      entry
                        ? { opacity: 1, x: entry.x, y: entry.y, width: entry.w, height: entry.h }
                        : { opacity: 0, x: c.x, y: y + 14, width: c.w - GAP, height: ROW_H - 8 }
                    }
                    animate={{ opacity: 1, x: c.x, y: y + 4, width: c.w - GAP, height: ROW_H - 8 }}
                    onClick={() => onSelect(m.cip)}
                    className={`absolute flex cursor-pointer items-center rounded-md px-2.5 ${
                      c.key === 'growth' ? 'border border-line' : ''
                    }`}
                    style={{ background: fill ?? wash ?? 'transparent' }}
                  >
                    <span
                      className="text-[13px] font-semibold"
                      style={{
                        color: fill ? inkFor(fill) : (tone ?? 'var(--ink2)'),
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {c.key === 'growth' && (
                        <span aria-hidden className="mr-1.5">
                          {growthOf(m.growth).glyph}
                        </span>
                      )}
                      {cellText(m, c.key)}
                      {c.key === 'exposure' && (
                        <span className="text-[10px] font-medium opacity-70"> /10</span>
                      )}
                    </span>
                  </motion.div>,
                )
              }
              return els
            })}
          </AnimatePresence>
        </div>
      </div>

      {rows.length === 0 && (
        <div className="grid h-44 place-items-center rounded-card border border-dashed border-line">
          <div className="text-center">
            <p className="text-sm text-ink2">No families selected.</p>
            <button
              onClick={() => setFams(new Set(allFamilies))}
              className="mt-2 text-[13px] font-medium text-accent hover:underline"
            >
              Show all families
            </button>
          </div>
        </div>
      )}
    </div>
  )
})

/** One quiet column label in the sticky header. Not interactive — sorting is
 *  the toolbar's SortMenu — so the sorted column only shifts color, never size,
 *  and no caret glyph competes with the label. */
function ColHeader({
  label,
  active,
  style,
}: {
  label: string
  active: boolean
  style: React.CSSProperties
}) {
  return (
    <div
      className={`micro absolute inset-y-0 flex items-center px-2 transition-colors ${
        active ? 'text-ink' : 'text-ink3'
      }`}
      style={style}
    >
      <span className="truncate">{label}</span>
    </div>
  )
}

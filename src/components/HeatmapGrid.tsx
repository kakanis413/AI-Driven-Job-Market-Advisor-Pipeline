import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { FAMILY_ORDER, REDUCED_TWEEN, SPRING, type Layer, type Mode } from '../design/tokens'
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
import type { Rect } from '../lib/layout'
import type { Family, Major, TipData } from '../types'

const ROW_H = 44
const HEAD_H = 34
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

interface Props {
  majors: Major[]
  width: number
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
  const cols = useMemo<Col[]>(() => {
    const weights: [ColKey, string, number][] = [
      ['exposure', 'AI exposure', 1.25],
      ['pay', 'Median pay', 1],
      ['completions', "Bachelor's grads / yr", 1],
    ]
    if (hasGrowth) weights.push(['growth', 'Job growth', 0.8])
    const total = weights.reduce((s, [, , w]) => s + w, 0)
    const space = bodyW - labelW
    let x = labelW
    return weights.map(([key, label, wt]) => {
      const w = (space * wt) / total
      const col = { key, label, x, w }
      x += w
      return col
    })
  }, [bodyW, labelW, hasGrowth])

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
    return sorted.map((m, i) => ({ m, y: HEAD_H + i * ROW_H }))
  }, [majors, fams, sort])

  const heroKey: ColKey = layer === 'pay' ? 'pay' : 'exposure'
  const heroCol = cols.find((c) => c.key === heroKey)!

  useEffect(() => {
    const g = geomRef.current
    g.clear()
    for (const { m, y } of rows)
      g.set(m.cip, { x: heroCol.x, y: y + 4, w: heroCol.w - GAP, h: ROW_H - 8 })
  }, [rows, heroCol, geomRef])

  const expC = useMemo(() => exposureColor(mode), [mode])
  const payC = useMemo(() => payColor(mode, payExtent), [mode, payExtent])
  const maxCompletions = useMemo(
    () => Math.max(...majors.map((m) => m.completions), 1),
    [majors],
  )

  const toggleSort = (key: SortKey) =>
    setSort((s) =>
      s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === 'major' ? 1 : -1 },
    )

  // Sort state is shown visually with ▲/▼ (aria-hidden); spell it out for
  // screen readers so the direction isn't lost when the glyph is skipped.
  const sortLabel = (key: SortKey, label: string) =>
    sort.key === key
      ? `${label}, sorted ${sort.dir === 1 ? 'ascending' : 'descending'} — activate to reverse`
      : `Sort by ${label.toLowerCase()}`

  const selIdx = rows.findIndex((r) => r.m.cip === selectedCip)
  const gridH = HEAD_H + rows.length * ROW_H

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
      {/* family filter chips */}
      <div className="mb-3 flex flex-wrap items-center gap-2" role="group" aria-label="Filter by family">
        {allFamilies.map((f) => {
          const on = fams.has(f)
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
                on
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

      <div
        className="overflow-x-auto"
        onPointerLeave={() => {
          setHoverRow(null)
          setHoverCol(null)
          onTip(null)
        }}
      >
        <div className="relative" style={{ width: bodyW, height: gridH }}>
          {/* column headers */}
          <button
            onClick={() => toggleSort('major')}
            aria-label={sortLabel('major', 'Major')}
            className={`micro absolute left-0 top-0 flex h-[26px] items-center gap-1 rounded-md px-2 text-left transition-colors ${
              sort.key === 'major' ? 'text-ink' : 'text-ink3 hover:text-ink'
            }`}
            style={{ width: labelW - GAP }}
          >
            Major {sort.key === 'major' && <span aria-hidden>{sort.dir === 1 ? '▲' : '▼'}</span>}
          </button>
          {cols.map((c) => (
            <button
              key={c.key}
              onClick={() => toggleSort(c.key)}
              aria-label={sortLabel(c.key, c.label)}
              className={`micro absolute top-0 flex h-[26px] items-center gap-1 rounded-md px-2 text-left transition-colors ${
                sort.key === c.key || hoverCol === c.key ? 'text-ink' : 'text-ink3 hover:text-ink'
              }`}
              style={{ left: c.x, width: c.w - GAP }}
            >
              {c.label}{' '}
              {sort.key === c.key && <span aria-hidden>{sort.dir === 1 ? '▲' : '▼'}</span>}
            </button>
          ))}

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
              animate={{ y: HEAD_H + hoverRow * ROW_H + 1 }}
              transition={spr}
            />
          )}
          {hoverCol !== null && (
            <motion.div
              className="pointer-events-none absolute rounded-lg"
              style={{
                top: HEAD_H,
                width: (cols.find((c) => c.key === hoverCol)?.w ?? 0) - GAP,
                height: rows.length * ROW_H,
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
              animate={{ y: HEAD_H + selIdx * ROW_H, height: ROW_H }}
              transition={spr}
            />
          )}

          <AnimatePresence>
            {rows.flatMap(({ m, y }, i) => {
              const delay = revealed ? 0 : Math.min(i * 0.022, 0.4)
              const hoverProps = (key: ColKey | null) => ({
                onPointerMove: (e: React.PointerEvent) => {
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
                const isHero = c.key === heroKey
                const entry = isHero ? entryGeom.current!.get(m.cip) : undefined
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

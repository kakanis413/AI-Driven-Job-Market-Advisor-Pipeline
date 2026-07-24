import { useMemo } from 'react'
import { bandOf, exposureColor, fmtExposure, fmtRatio, normalize } from '../design/scales'
import { TABLE_HEAD_H, TABLE_ROW_H, type Mode } from '../design/tokens'
import type { Major } from '../types'
import DataChip from './DataChip'

/** Shared column template — header and rows use the exact same track sizes so
 *  every value lines up with its header, and the two numeric columns
 *  (pay-vs-debt ×, exposure) right-align to their own consistent edge. */
const COLS = 'grid-cols-[2rem_minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_7rem]'

export type SortKey = 'payToDebt' | 'versatility'

/** A ranked leaderboard of majors by their two "value" metrics — pay-to-debt
 *  and career versatility — each shown as a labeled neutral meter, with the AI
 *  exposure score trailing so the app's through-line stays present. This is the
 *  third view mode (alongside Heatmap/HashTable); it surfaces the meters that
 *  otherwise only appear once a single major is opened. Rows are clickable →
 *  detail/advisor. Sort is controlled from the toolbar's "Sort by" segment. */
export default function MetersView({
  majors,
  height,
  query,
  sort,
  mode,
  onSortChange,
  onSelect,
}: {
  majors: Major[]
  height: number
  query: string
  sort: SortKey
  mode: Mode
  onSortChange: (k: SortKey) => void
  onSelect: (cip: string) => void
}) {
  const expC = useMemo(() => exposureColor(mode), [mode])

  const q = normalize(query)
  const rows = useMemo(() => {
    // Leaderboard order: highest metric first, so the rank column reads #1 = top.
    const val = (m: Major) => (sort === 'payToDebt' ? m.payToDebt : m.versatility) ?? -1
    return majors
      .filter((m) => m.payToDebt != null || m.versatility != null)
      .filter((m) => !q || normalize(m.major).includes(q) || normalize(m.family).includes(q))
      .sort((a, b) => val(b) - val(a))
  }, [majors, q, sort])

  if (rows.length === 0)
    return (
      <div style={{ height }} className="grid place-items-center">
        <p className="text-sm text-ink3">No pay-to-debt or versatility data for this selection.</p>
      </div>
    )

  return (
    <div
      style={{ maxHeight: height }}
      className="w-full overflow-y-auto"
      role="table"
      aria-label="Majors ranked by pay-to-debt and career versatility"
    >
      {/* Full-bleed and left-aligned to the same edge as the Heatmap/HashTable
          views, so switching tabs never shifts the content. No enclosing card —
          the hairline rows carry the structure, matching the grid. */}
      <div
        role="row"
        style={{ height: TABLE_HEAD_H }}
        className={`sticky top-0 z-20 grid ${COLS} items-center gap-5 border-b border-line bg-page/95 px-2 backdrop-blur`}
      >
        <span className="micro text-right text-ink3">#</span>
        <span className="micro text-ink3">Major</span>
        <SortHeader
          label="Pay vs. debt"
          active={sort === 'payToDebt'}
          onClick={() => onSortChange('payToDebt')}
        />
        <SortHeader
          label="Career versatility"
          active={sort === 'versatility'}
          onClick={() => onSortChange('versatility')}
        />
        <span className="micro justify-self-end text-ink3">Exposure</span>
      </div>

      <ul>
        {rows.map((m, i) => (
          <li key={m.cip} role="row">
            <button
              onClick={() => onSelect(m.cip)}
              style={{ height: TABLE_ROW_H }}
              className={`grid w-full ${COLS} items-center gap-5 rounded-md border-b border-line px-2 text-left transition-colors last:border-b-0 hover:bg-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page`}
            >
              <span
                className="text-right text-[13px] font-semibold text-ink3"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {i + 1}
              </span>
              {/* Same two-line label treatment as the Table's row label —
                  leading-tight so the name + family pair sits centered in the
                  shared row height. */}
              <span className="flex min-w-0 flex-col justify-center">
                <span className="truncate text-[13px] font-medium leading-tight text-ink">
                  {m.major}
                </span>
                <span className="micro truncate text-ink3">{m.family}</span>
              </span>
              <RowMeter
                fill={m.payToDebtRank ?? 0}
                value={m.payToDebt != null ? fmtRatio(m.payToDebt) : null}
              />
              <RowMeter
                fill={m.versatilityRank ?? 0}
                value={m.versatility != null ? bandOf(m.versatility) : null}
              />
              <ExposureCell value={m.exposure} color={expC(m.exposure)} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function SortHeader({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`micro inline-flex items-center gap-1 justify-self-start transition-colors ${
        active ? 'text-ink' : 'text-ink3 hover:text-ink2'
      }`}
    >
      <span className="truncate">{label}</span>
      {/* Same always-reserved caret slot as the Table's sort bar, so the two
          views' headers read identically. This board sorts descending only. */}
      <span aria-hidden className={`shrink-0 ${active ? 'opacity-100' : 'opacity-0'}`}>
        ▼
      </span>
    </button>
  )
}

/* Compact meter for a board row: neutral ink bar + value text. Same neutral
   fill as the detail card's meters — never the exposure/pay ramp (hard rule 5).
   With no value, the whole cell becomes a "No data" chip instead of an empty bar
   and a lone dash. */
function RowMeter({ fill, value }: { fill: number; value: string | null }) {
  if (value === null)
    return (
      <span className="flex items-center">
        <DataChip label="No data" />
      </span>
    )
  return (
    <span className="flex items-center gap-3">
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-line" aria-hidden>
        <span
          className="block h-full rounded-full bg-ink2"
          style={{ width: `${Math.max(0, Math.min(1, fill)) * 100}%` }}
        />
      </span>
      {/* Fixed-width, right-aligned readout: the numbers stack on one edge down
          the column instead of drifting with each bar's length. */}
      <span
        className="w-16 shrink-0 text-right text-[13px] font-semibold text-ink"
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </span>
    </span>
  )
}

/* Trailing exposure readout: the violet ramp dot paired with the one-decimal
   score (color is never the only signal, hard rule 2). A dot, not a filled bar,
   so the ramp stays a small indicator and never encodes area on a data row. */
function ExposureCell({ value, color }: { value: number | null; color: string }) {
  if (value === null)
    return (
      <span className="flex items-center justify-end">
        <DataChip label="Not scored" />
      </span>
    )
  return (
    <span
      className="flex items-center justify-end gap-2 text-[13px] font-semibold text-ink"
      style={{ fontVariantNumeric: 'tabular-nums' }}
      aria-label={`exposure ${fmtExposure(value)} out of 10`}
    >
      <span aria-hidden className="size-2 shrink-0 rounded-full" style={{ background: color }} />
      {/* Same fixed-width right-aligned treatment as the meter readouts. */}
      <span className="w-7 text-right">{fmtExposure(value)}</span>
    </span>
  )
}

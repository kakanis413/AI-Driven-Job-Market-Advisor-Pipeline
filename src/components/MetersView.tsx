import { useMemo, useState } from 'react'
import { bandOf, fmtRatio, normalize } from '../design/scales'
import type { Major } from '../types'

type SortKey = 'payToDebt' | 'versatility'

/** A ranked board of majors by their two "value" metrics — pay-to-debt and
 *  career versatility — each shown as a labeled meter. This is the third view
 *  mode (alongside Treemap/Heatmap); it surfaces the meters that otherwise only
 *  appear once a single major is opened. Rows are clickable → detail/advisor. */
export default function MetersView({
  majors,
  height,
  query,
  onSelect,
}: {
  majors: Major[]
  height: number
  query: string
  onSelect: (cip: string) => void
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'payToDebt', dir: -1 })

  const q = normalize(query)
  const rows = useMemo(() => {
    const val = (m: Major, k: SortKey) =>
      (k === 'payToDebt' ? m.payToDebt : m.versatility) ?? -1
    return majors
      .filter((m) => m.payToDebt != null || m.versatility != null)
      .filter((m) => !q || normalize(m.major).includes(q) || normalize(m.family).includes(q))
      .sort((a, b) => (val(a, sort.key) - val(b, sort.key)) * sort.dir)
  }, [majors, q, sort])

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: -1 }))

  if (rows.length === 0)
    return (
      <div style={{ height }} className="grid place-items-center">
        <p className="text-sm text-ink3">No pay-to-debt or versatility data for this selection.</p>
      </div>
    )

  return (
    <div
      style={{ maxHeight: height }}
      className="overflow-y-auto rounded-card border border-line bg-surface"
      role="table"
      aria-label="Majors ranked by pay-to-debt and career versatility"
    >
      <div
        role="row"
        className="sticky top-0 z-10 grid grid-cols-[1fr_8rem_8rem] items-center gap-4 border-b border-line bg-surface/95 px-4 py-2.5 backdrop-blur sm:grid-cols-[1fr_11rem_11rem]"
      >
        <span className="micro text-ink3">Major</span>
        <SortHeader label="Pay vs. debt" active={sort.key === 'payToDebt'} dir={sort.dir} onClick={() => toggleSort('payToDebt')} />
        <SortHeader label="Career versatility" active={sort.key === 'versatility'} dir={sort.dir} onClick={() => toggleSort('versatility')} />
      </div>

      <ul>
        {rows.map((m) => (
          <li key={m.cip} role="row">
            <button
              onClick={() => onSelect(m.cip)}
              className="grid w-full grid-cols-[1fr_8rem_8rem] items-center gap-4 border-b border-line px-4 py-2.5 text-left transition-colors last:border-b-0 hover:bg-raised sm:grid-cols-[1fr_11rem_11rem]"
            >
              <span className="min-w-0">
                <span className="block truncate text-[13.5px] font-medium text-ink">{m.major}</span>
                <span className="micro text-ink3">{m.family}</span>
              </span>
              <RowMeter
                fill={m.payToDebtRank ?? 0}
                value={m.payToDebt != null ? fmtRatio(m.payToDebt) : '—'}
              />
              <RowMeter
                fill={m.versatilityRank ?? 0}
                value={m.versatility != null ? bandOf(m.versatilityRank ?? 0) : '—'}
              />
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
  dir,
  onClick,
}: {
  label: string
  active: boolean
  dir: 1 | -1
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
      {label}
      <span aria-hidden className={active ? 'opacity-100' : 'opacity-0'}>
        {dir === -1 ? '↓' : '↑'}
      </span>
    </button>
  )
}

/* Compact meter for a board row: neutral ink bar + value text. Same neutral
   fill as the detail card's meters — never the exposure/pay ramp. */
function RowMeter({ fill, value }: { fill: number; value: string }) {
  return (
    <span className="flex items-center gap-2">
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-line" aria-hidden>
        <span
          className="block h-full rounded-full bg-ink2"
          style={{ width: `${Math.max(0, Math.min(1, fill)) * 100}%` }}
        />
      </span>
      <span
        className="w-14 shrink-0 text-right text-[13px] font-semibold text-ink"
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </span>
    </span>
  )
}

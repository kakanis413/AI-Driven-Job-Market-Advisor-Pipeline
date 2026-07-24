import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'

export interface SortOption {
  key: string
  label: string
  /** Text sorts read "A to Z"; numeric ones read "High to low". */
  text?: boolean
}

/** The Table's sort control: one trigger that opens a floating panel of columns
 *  plus a direction pair. It replaces per-header carets — the sort is stated in
 *  words ("AI exposure · high to low") instead of a glyph you have to decode,
 *  and the column headers stay quiet labels. The panel floats, so glass is
 *  legitimate here (hard rule 5). */
export default function SortMenu({
  options,
  sortKey,
  dir,
  onChange,
}: {
  options: SortOption[]
  sortKey: string
  dir: 1 | -1
  onChange: (key: string, dir: 1 | -1) => void
}) {
  const reduce = useReducedMotion()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)

  const active = options.find((o) => o.key === sortKey) ?? options[0]
  const dirLabel = (d: 1 | -1) =>
    active?.text ? (d === 1 ? 'A to Z' : 'Z to A') : d === 1 ? 'Low to high' : 'High to low'

  // Esc closes and returns focus to the trigger; a click outside just closes.
  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      setOpen(false)
      btnRef.current?.focus()
    }
    window.addEventListener('pointerdown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('pointerdown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const ring =
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page'

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        ref={btnRef}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`Sort table — currently ${active?.label}, ${dirLabel(dir).toLowerCase()}`}
        className={`micro inline-flex h-8 items-center gap-1.5 rounded-full border border-line bg-surface px-3 text-ink2 transition-colors hover:text-ink ${ring}`}
      >
        <SlidersIcon />
        Sort
        <span className="text-ink3">·</span>
        <span className="text-ink">{active?.label}</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-label="Sort table"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            transition={{ duration: reduce ? 0.12 : 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="glass absolute left-0 top-10 z-30 w-56 rounded-card p-2 shadow-xl"
          >
            <div className="micro px-2 pb-1.5 pt-1 text-ink3">Sort by</div>
            <ul>
              {options.map((o) => {
                const on = o.key === sortKey
                return (
                  <li key={o.key}>
                    <button
                      role="radio"
                      aria-checked={on}
                      // Keep the direction when switching fields, so the reading
                      // order the student picked survives the change.
                      onClick={() => onChange(o.key, dir)}
                      className={`flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-raised ${ring}`}
                    >
                      <span
                        aria-hidden
                        className={`grid size-4 shrink-0 place-items-center rounded-full border transition-colors ${
                          on ? 'border-transparent bg-ink text-page' : 'border-line'
                        }`}
                      >
                        {on && <span className="size-1.5 rounded-full bg-page" />}
                      </span>
                      <span className="micro truncate text-ink2">{o.label}</span>
                    </button>
                  </li>
                )
              })}
            </ul>

            <div className="my-1.5 border-t border-line" />
            <div className="micro px-2 pb-1.5 text-ink3">Order</div>
            <div className="flex gap-1 px-1 pb-1">
              {([-1, 1] as const).map((d) => (
                <button
                  key={d}
                  aria-pressed={dir === d}
                  onClick={() => onChange(sortKey, d)}
                  className={`micro h-8 flex-1 rounded-md border transition-colors ${ring} ${
                    dir === d
                      ? 'border-transparent bg-ink text-page'
                      : 'border-line text-ink2 hover:text-ink'
                  }`}
                >
                  {dirLabel(d)}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function SlidersIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden className="shrink-0">
      <path
        d="M2 4.5h5.4M11.4 4.5H14M2 11.5h2.6M8.6 11.5H14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <circle cx="9.4" cy="4.5" r="1.7" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="6.6" cy="11.5" r="1.7" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

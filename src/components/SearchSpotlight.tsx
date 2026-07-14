import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { exposureColor, fmtExposure, normalize } from '../design/scales'
import type { Mode } from '../design/tokens'
import type { Major } from '../types'

interface Props {
  majors: Major[]
  mode: Mode
  query: string
  onQuery: (q: string) => void
  onPick: (m: Major) => void
}

export default function SearchSpotlight({ majors, mode, query, onQuery, onPick }: Props) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const expC = useMemo(() => exposureColor(mode), [mode])

  const q = normalize(query)
  const matches = useMemo(
    () =>
      q
        ? majors
            .filter((m) => normalize(m.major).includes(q) || normalize(m.family).includes(q))
            .slice(0, 8)
        : [],
    [majors, q],
  )

  // "/" focuses the search from anywhere
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLTextAreaElement)) {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const pick = (m: Major) => {
    onPick(m)
    setOpen(false)
    inputRef.current?.blur()
  }

  return (
    <div className="relative">
      <div className="flex h-12 items-center gap-3 rounded-xl border border-line bg-surface px-4 shadow-sm transition-shadow focus-within:border-accent focus-within:shadow-md">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden className="shrink-0 text-ink3">
          <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.6" />
          <path d="M11 11l3.2 3.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded={open && matches.length > 0}
          aria-controls="major-search-listbox"
          aria-label="Find your major"
          aria-activedescendant={open && matches[active] ? `major-opt-${matches[active].cip}` : undefined}
          className="h-full w-full bg-transparent text-[15px] text-ink outline-none placeholder:text-ink3"
          placeholder="Find your major…"
          value={query}
          onChange={(e) => {
            onQuery(e.target.value)
            setOpen(true)
            setActive(0)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((a) => Math.min(a + 1, matches.length - 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((a) => Math.max(a - 1, 0))
            } else if (e.key === 'Enter' && matches[active]) {
              e.preventDefault()
              pick(matches[active])
            } else if (e.key === 'Escape') {
              onQuery('')
              setOpen(false)
            }
          }}
        />
        <kbd className="micro hidden rounded border border-line px-1.5 py-0.5 text-ink3 sm:block" aria-hidden>
          /
        </kbd>
      </div>

      <AnimatePresence>
        {open && q && (
          <motion.ul
            id="major-search-listbox"
            role="listbox"
            aria-label="Matching majors"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="absolute z-30 mt-2 w-full overflow-hidden rounded-card border border-line bg-raised p-1 shadow-xl"
          >
            {matches.length === 0 && (
              <li className="px-3 py-3 text-[13px] text-ink3">No majors match “{query}”.</li>
            )}
            {matches.map((m, i) => (
              <li key={m.cip} role="option" id={`major-opt-${m.cip}`} aria-selected={i === active}>
                <button
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left ${
                    i === active ? 'bg-accent-soft' : 'hover:bg-accent-soft'
                  }`}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => pick(m)}
                >
                  <span
                    aria-hidden
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ background: expC(m.exposure) }}
                  />
                  <span className="flex-1 truncate text-[14px] font-medium text-ink">{m.major}</span>
                  <span className="micro text-ink3">{m.family}</span>
                  <span className="text-[13px] font-semibold text-ink" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {fmtExposure(m.exposure)}
                  </span>
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  )
}

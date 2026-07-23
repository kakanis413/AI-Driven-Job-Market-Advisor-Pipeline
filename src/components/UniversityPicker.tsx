import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { normalize } from '../design/scales'
import { useUniversities, type University } from '../hooks/useUniversities'

interface Props {
  /** Controlled query text (the input's value). */
  query: string
  onQuery: (q: string) => void
  /** Fired when a school is chosen from the list. */
  onPick: (u: University) => void
  /** Autofocus on mount (the modal opens straight onto it). */
  autoFocus?: boolean
}

/** School combobox — the same pattern as SearchSpotlight (glass, tokens,
 *  ↑/↓/Enter/Esc, ARIA combobox/listbox/option), filtering the local
 *  /universities.json list by name. Nothing here should feel new. */
export default function UniversityPicker({ query, onQuery, onPick, autoFocus }: Props) {
  const reduce = useReducedMotion()
  const { universities, status } = useUniversities()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (autoFocus) inputRef.current?.focus()
  }, [autoFocus])

  const q = normalize(query)
  const matches = useMemo(
    () =>
      q
        ? universities
            .filter((u) => normalize(u.name).includes(q) || normalize(u.state).includes(q))
            .slice(0, 8)
        : [],
    [universities, q],
  )

  const pick = (u: University) => {
    onPick(u)
    setOpen(false)
    inputRef.current?.blur()
  }

  return (
    <div className="relative">
      <div className="flex h-11 items-center gap-2.5 rounded-xl border border-line bg-surface px-3.5 transition-shadow focus-within:border-accent focus-within:shadow-md">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden className="shrink-0 text-ink3">
          <path d="M8 2 1.5 5 8 8l6.5-3L8 2Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
          <path d="M4.5 6.6V10c0 .9 1.6 1.6 3.5 1.6s3.5-.7 3.5-1.6V6.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded={open && matches.length > 0}
          aria-controls="university-listbox"
          aria-label="Find your university"
          aria-activedescendant={open && matches[active] ? `uni-opt-${matches[active].unitid}` : undefined}
          className="h-full w-full bg-transparent text-[15px] text-ink outline-none placeholder:text-ink3"
          placeholder={status === 'loading' ? 'Loading universities…' : 'Find your university…'}
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
            } else if (e.key === 'Escape' && open && q) {
              // Close the list first; a second Esc bubbles to the modal to dismiss.
              e.stopPropagation()
              setOpen(false)
            }
          }}
        />
      </div>

      <AnimatePresence>
        {open && q && (
          <motion.ul
            id="university-listbox"
            role="listbox"
            aria-label="Matching universities"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            transition={{ duration: reduce ? 0.12 : 0.18, ease: [0.22, 1, 0.36, 1] }}
            className="absolute z-30 mt-2 max-h-72 w-full overflow-auto rounded-card border border-line bg-raised p-1 shadow-xl"
          >
            {matches.length === 0 && (
              <li className="px-3 py-3 text-[13px] text-ink3">
                {status === 'error' ? 'Couldn’t load the university list.' : `No universities match “${query}”.`}
              </li>
            )}
            {matches.map((u, i) => (
              <li key={u.unitid} role="option" id={`uni-opt-${u.unitid}`} aria-selected={i === active}>
                <button
                  type="button"
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left ${
                    i === active ? 'bg-accent-soft' : 'hover:bg-accent-soft'
                  }`}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => pick(u)}
                >
                  <span className="min-w-0 flex-1 truncate text-[14px] font-medium text-ink">{u.name}</span>
                  <span className="micro shrink-0 text-ink3">{u.state}</span>
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  )
}

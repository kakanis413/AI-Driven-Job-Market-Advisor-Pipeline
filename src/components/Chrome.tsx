/** Shared top-bar chrome: the wordmark/logo and the nav cluster. Extracted so
 *  both the global header (landing/news, in App) and the Explore page's single
 *  combined bar render the exact same logo and navigation. */

import { EXPOSURE_STOPS, type Mode } from '../design/tokens'
import type { Page } from '../hooks/useRoute'

export function Wordmark({ mode }: { mode: Mode }) {
  const s = EXPOSURE_STOPS[mode]
  return (
    <svg width="20" height="20" viewBox="0 0 32 32" aria-hidden>
      <rect x="2" y="2" width="17" height="17" rx="4" fill={s[0]} />
      <rect x="21" y="2" width="9" height="11" rx="3" fill={s[2]} />
      <rect x="2" y="21" width="11" height="9" rx="3" fill={s[3]} />
      <rect x="15" y="21" width="15" height="9" rx="3" fill={s[4]} />
    </svg>
  )
}

export function Logo({ mode, onHome }: { mode: Mode; onHome: () => void }) {
  return (
    <button
      onClick={onHome}
      aria-label="Major Visualizer — back to start"
      className="flex shrink-0 items-center gap-2.5 rounded-md"
    >
      <Wordmark mode={mode} />
      <span className="text-[16px] tracking-tight text-ink">
        <span className="font-display pr-[0.04em] text-[17px] text-accent">Major</span>
        <span className="font-semibold">Visualizer</span>
      </span>
    </button>
  )
}

/** Nav (Explore / News) + theme toggle. The nav is deliberately quiet — plain
 *  text with a thin underline for the active page — so it never competes with
 *  the dark-filled *controls*, which own the "what I selected" signal. */
export function NavCluster({
  page,
  mode,
  onNav,
  onToggle,
}: {
  page: Page
  mode: Mode
  onNav: (p: Page) => void
  onToggle: () => void
}) {
  return (
    <div className="flex shrink-0 items-center gap-1">
      <nav className="hidden items-center sm:flex">
        {(['explore', 'news'] as const).map((p) => {
          const active = page === p
          return (
            <button
              key={p}
              onClick={() => onNav(p)}
              aria-current={active ? 'page' : undefined}
              className={`relative rounded-md px-3 py-1.5 text-[13px] font-medium capitalize transition-colors ${
                active ? 'text-ink' : 'text-ink3 hover:text-ink2'
              }`}
            >
              {p}
              {active && (
                <span
                  aria-hidden
                  className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-ink"
                />
              )}
            </button>
          )
        })}
      </nav>
      <button
        onClick={onToggle}
        aria-label={`Switch to ${mode === 'dark' ? 'light' : 'dark'} mode`}
        className="grid size-9 place-items-center rounded-full border border-line bg-surface/60 text-ink2 transition-colors hover:text-ink"
      >
        {mode === 'dark' ? <SunIcon /> : <MoonIcon />}
      </button>
    </div>
  )
}

function SunIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
      <circle cx="7.5" cy="7.5" r="3.2" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M7.5 1v1.8M7.5 12.2V14M14 7.5h-1.8M2.8 7.5H1m11.1-4.6-1.3 1.3M4.2 10.8l-1.3 1.3m9.2 0-1.3-1.3M4.2 4.2 2.9 2.9"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
      <path
        d="M13 9.5A6 6 0 1 1 5.5 2 4.8 4.8 0 0 0 13 9.5Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

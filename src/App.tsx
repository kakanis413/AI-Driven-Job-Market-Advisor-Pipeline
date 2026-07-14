import { AnimatePresence, motion } from 'framer-motion'
import Landing from './pages/Landing'
import Explore from './pages/Explore'
import { EXPOSURE_STOPS, type Mode } from './design/tokens'
import { useMajors } from './hooks/useMajors'
import { useRoute } from './hooks/useRoute'
import { useTheme } from './hooks/useTheme'

const EASE = [0.22, 1, 0.36, 1] as const

export default function App() {
  const { status, majors, retry, url } = useMajors()
  const { mode, toggle } = useTheme()
  const { page, sub, nav } = useRoute()

  return (
    <div className="min-h-screen pb-20">
      <header className="relative z-20 mx-auto flex max-w-[1400px] items-center justify-between px-5 pt-5 md:px-8">
        <button
          onClick={() => nav('landing')}
          aria-label="Major Visualizer — back to start"
          className="flex items-center gap-2.5 rounded-md"
        >
          <Wordmark mode={mode} />
          <span className="text-[15px] font-semibold tracking-tight text-ink">Major Visualizer</span>
          <span className="micro mt-px hidden rounded-full border border-line px-2 py-0.5 text-ink3 sm:block">
            Sample data
          </span>
        </button>
        <div className="flex items-center gap-2">
          {page === 'landing' && (
            <button
              onClick={() => nav('explore')}
              className="hidden h-9 items-center rounded-[10px] border border-line bg-surface px-3.5 text-[13px] font-medium text-ink2 transition-colors hover:text-ink sm:flex"
            >
              Explore
            </button>
          )}
          <button
            onClick={toggle}
            aria-label={`Switch to ${mode === 'dark' ? 'light' : 'dark'} mode`}
            className="grid size-9 place-items-center rounded-[10px] border border-line bg-surface text-ink2 transition-colors hover:text-ink"
          >
            {mode === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </header>

      <AnimatePresence mode="wait">
        {page === 'landing' ? (
          <motion.div
            key="landing"
            exit={{ opacity: 0, y: -18 }}
            transition={{ duration: 0.28, ease: EASE }}
          >
            <Landing majors={majors} mode={mode} onExplore={(s) => nav('explore', s)} />
          </motion.div>
        ) : (
          <motion.div
            key="explore"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.32, ease: EASE }}
          >
            <Explore
              majors={majors}
              status={status}
              url={url}
              retry={retry}
              mode={mode}
              initialView={sub === 'heatmap' ? 'grid' : 'map'}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Hard rule 4: the caveat is pinned and always visible. */}
      <footer className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] items-center gap-2.5 px-5 py-2.5 md:px-8">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden className="shrink-0 text-ink3">
            <path d="M7 1.2 13.3 12H.7L7 1.2Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
            <path d="M7 5.5v3M7 10.3v.2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
          <p className="text-[12px] leading-snug text-ink2">
            <b className="font-semibold text-ink">High exposure does not mean the job disappears.</b>{' '}
            It means the mix of tasks in that field is likely to change. Sample data, for
            illustration — not career advice.
          </p>
        </div>
      </footer>
    </div>
  )
}

function Wordmark({ mode }: { mode: Mode }) {
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

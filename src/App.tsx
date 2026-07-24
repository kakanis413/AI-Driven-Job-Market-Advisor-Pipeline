import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import Landing from './pages/Landing'
import Explore from './pages/Explore'
import News from './pages/News'
import Chat from './pages/Chat'
import { Logo, NavCluster } from './components/Chrome'
import { FAMILY_ORDER } from './design/tokens'
import type { Family } from './types'
import type { Page } from './hooks/useRoute'

const isFamily = (s: string | null): s is Family =>
  s !== null && (FAMILY_ORDER as string[]).includes(s)
import { useMajors } from './hooks/useMajors'
import { useRoute } from './hooks/useRoute'
import { useTheme } from './hooks/useTheme'

const EASE = [0.22, 1, 0.36, 1] as const

export default function App() {
  const { status, majors, retry, url } = useMajors()
  const { mode, toggle } = useTheme()
  const { page, sub, nav } = useRoute()
  // How the landing hands off to Explore: a search query, a specific major to
  // select, or "just open the advisor". Consumed once when Explore mounts and
  // cleared on a plain Explore nav so nothing persists unexpectedly.
  const [exploreQuery, setExploreQuery] = useState('')
  const [selectCip, setSelectCip] = useState<string | undefined>(undefined)
  const [autoAdvisor, setAutoAdvisor] = useState(false)
  const goExplore = (query = '') => {
    setExploreQuery(query)
    setSelectCip(undefined)
    setAutoAdvisor(false)
    nav('explore')
  }
  const selectMajor = (cip: string) => {
    setExploreQuery('')
    setSelectCip(cip)
    setAutoAdvisor(false)
    nav('explore')
  }
  const openAdvisor = () => {
    setExploreQuery('')
    setSelectCip(undefined)
    setAutoAdvisor(true)
    nav('explore')
  }
  const onNav = (p: Page) => (p === 'explore' ? goExplore() : nav(p))

  return (
    <div className="min-h-screen pb-20">
      {/* Bypass block (WCAG 2.4.1): first Tab stop jumps keyboard users past the
          header/nav straight to the page content. Visually hidden until focused. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-[70] focus:rounded-lg focus:border focus:border-line focus:bg-raised focus:px-4 focus:py-2 focus:text-[13px] focus:font-semibold focus:text-ink focus:shadow-lg"
      >
        Skip to content
      </a>
      {/* On Explore the logo + nav live inside that page's single combined bar,
          so the global header only renders on landing / news. */}
      {page !== 'explore' && (
        <header className="glass sticky top-0 z-40 border-x-0 border-t-0">
          <div className="mx-auto flex max-w-[1400px] items-center justify-between px-5 py-2.5 md:px-8">
            <Logo
              mode={mode}
              onHome={() => nav('landing')}
              context={page === 'news' ? 'News' : page === 'chat' ? 'Chat' : undefined}
            />
            <NavCluster page={page} mode={mode} onNav={onNav} onToggle={toggle} />
          </div>
        </header>
      )}

      <main id="main-content" tabIndex={-1} className="outline-none">
      <AnimatePresence mode="wait">
        {page === 'landing' ? (
          <motion.div
            key="landing"
            exit={{ opacity: 0, y: -18 }}
            transition={{ duration: 0.28, ease: EASE }}
          >
            <Landing
              majors={majors}
              mode={mode}
              onExplore={goExplore}
              onSelectMajor={selectMajor}
              onOpenAdvisor={openAdvisor}
            />
          </motion.div>
        ) : page === 'news' ? (
          <motion.div
            key="news"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.32, ease: EASE }}
          >
            <News
              family={isFamily(sub) ? sub : 'STEM'}
              onFamily={(f) => nav('news', f)}
            />
          </motion.div>
        ) : page === 'chat' ? (
          <motion.div
            key="chat"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.32, ease: EASE }}
          >
            <Chat majors={majors} mode={mode} initialCip={sub} />
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
              nav={nav}
              toggle={toggle}
              initialQuery={exploreQuery}
              initialSelectedCip={selectCip}
              autoAdvisor={autoAdvisor}
              initialView={sub === 'heatmap' ? 'grid' : 'map'}
            />
          </motion.div>
        )}
      </AnimatePresence>
      </main>

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

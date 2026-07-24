import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { Segmented } from '../components/LayerToggle'
import NewsList from '../components/NewsList'
import { FAMILY_ORDER } from '../design/tokens'
import { fetchNews, newsIsLive, type NewsFeed } from '../lib/news'
import type { Family } from '../types'

/** News tab: per-family, precomputed on the backend, deep-linkable via
 *  `#/news/{family}` so the advisor chat CTA can preselect (NEWS_TAB.md §5). */
export default function News({
  family,
  onFamily,
}: {
  family: Family
  onFamily: (f: Family) => void
}) {
  const reduce = useReducedMotion()
  const [feed, setFeed] = useState<NewsFeed | null>(null)
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('loading')
  const [nonce, setNonce] = useState(0) // bump to retry

  useEffect(() => {
    if (!newsIsLive) {
      setState('error')
      return
    }
    const ctrl = new AbortController()
    setState('loading')
    fetchNews(family, ctrl.signal)
      .then((f) => {
        setFeed(f)
        setState('idle')
      })
      .catch((e: unknown) => {
        if (!(e instanceof DOMException && e.name === 'AbortError')) setState('error')
      })
    return () => ctrl.abort()
  }, [family, nonce])

  const retry = useCallback(() => setNonce((n) => n + 1), [])

  return (
    <div className="mx-auto max-w-[1100px] px-5 pt-6 md:px-8">
      {/* No page title band: the app header already reads "Major Visualizer ·
          News", so the field selector is the top of the page and the one-liner
          rides under it as helper text rather than a second header. */}
      <div className="overflow-x-auto pb-1">
        <Segmented<Family>
          label="Field"
          size="lg"
          value={family}
          onChange={onFamily}
          options={FAMILY_ORDER.map((f) => ({ value: f, label: f }))}
        />
      </div>
      <p className="mt-2.5 text-[13px] text-ink3">
        Recent, cited signal on how AI is changing careers — by field of study.
      </p>

      <AnimatePresence mode="wait">
        <motion.div
          key={family}
          className="mt-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduce ? 0.15 : 0.25 }}
        >
          <NewsList
            items={feed?.family === family ? feed.items : []}
            fetchedAt={feed?.family === family ? feed.fetched_at : null}
            state={state}
            onRetry={retry}
          />
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

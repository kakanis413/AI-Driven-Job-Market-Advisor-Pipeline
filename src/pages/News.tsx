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
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle')
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
    <div className="mx-auto max-w-[720px] px-5 pt-10 md:px-8">
      <h1 className="text-[26px] font-semibold tracking-tight text-ink">News</h1>
      <p className="mt-1 text-[14px] text-ink2">
        Recent, cited signal on how AI is changing careers — by field of study.
      </p>

      <div className="mt-5 overflow-x-auto pb-1">
        <Segmented<Family>
          label="Field"
          value={family}
          onChange={onFamily}
          options={FAMILY_ORDER.map((f) => ({ value: f, label: f }))}
        />
      </div>

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

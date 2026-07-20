import { motion, useReducedMotion } from 'framer-motion'
import { EASE } from '../design/tokens'
import type { NewsItem } from '../lib/news'
import NewsCard from './NewsCard'

/** Renders NewsCards plus the honest surrounding states (NEWS_TAB.md §4):
 *  skeletons while loading, "no items" as a fact not an error, an error state
 *  with retry, and `fetched_at` always visible so age is never hidden. */
export default function NewsList({
  items,
  variant = 'full',
  fetchedAt = null,
  state = 'idle',
  onRetry,
}: {
  items: NewsItem[]
  variant?: 'compact' | 'full'
  fetchedAt?: string | null
  state?: 'idle' | 'loading' | 'error'
  onRetry?: () => void
}) {
  const reduce = useReducedMotion()

  if (state === 'loading') {
    return (
      <div aria-busy="true">
        <p className="micro mb-3 text-ink3" role="status">
          Searching live sources…
        </p>
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="animate-pulse rounded-card border border-line bg-raised p-3">
              <div className="h-4 w-3/4 rounded bg-line" />
              <div className="mt-2.5 h-3 w-1/3 rounded bg-line" />
              {variant === 'full' && <div className="mt-2.5 h-3 w-full rounded bg-line" />}
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (state === 'error') {
    return (
      <div className="rounded-card border border-dashed border-line p-4 text-[13px] text-ink2">
        Couldn’t load news.
        {onRetry && (
          <button
            onClick={onRetry}
            className="ml-2 font-semibold text-accent hover:underline"
          >
            Retry
          </button>
        )}
      </div>
    )
  }

  return (
    <div>
      {fetchedAt && (
        <p className="micro mb-3 text-ink3">Updated {relative(fetchedAt)}</p>
      )}
      {items.length === 0 ? (
        <p className="rounded-card border border-dashed border-line p-4 text-[13px] text-ink2">
          No recent items for this field.
        </p>
      ) : (
        <div className="space-y-4">
          {items.map((item, i) => (
            <motion.div
              key={item.url}
              initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={
                reduce
                  ? { duration: 0.15 }
                  : { duration: 0.3, ease: EASE, delay: Math.min(i * 0.014, 0.45) }
              }
            >
              <NewsCard item={item} variant={variant} />
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}

function relative(iso: string): string {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`
}

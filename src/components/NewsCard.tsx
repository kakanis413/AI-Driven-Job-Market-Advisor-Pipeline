import type { NewsItem } from '../lib/news'

/** One cited news item — the shared atom for the News tab (`full`) and the
 *  advisor chat (`compact`). A single <a> wraps the whole card: one tab stop.
 *  Items without a URL never reach this component (dropped upstream). */
export default function NewsCard({
  item,
  variant = 'full',
}: {
  item: NewsItem
  variant?: 'compact' | 'full'
}) {
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${item.title} — ${item.source}, opens in new tab`}
      className="group block rounded-card border border-line bg-raised p-3 transition-colors duration-150 hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-[13.5px] font-semibold leading-snug text-ink transition-colors duration-150 group-hover:text-accent group-visited:text-ink2">
          {item.title}
        </span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          aria-hidden
          className="mt-0.5 shrink-0 text-ink3 transition-colors duration-150 group-hover:text-accent"
        >
          <path
            d="M4.5 2H10m0 0v5.5M10 2 2 10"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <div className="micro mt-2 text-ink3">
        {item.source}
        {item.published && (
          <>
            {' · '}
            <time dateTime={item.published}>{fmtDate(item.published)}</time>
          </>
        )}
      </div>
      {variant === 'full' && item.summary && (
        <p className="mt-2 text-[12.5px] leading-relaxed text-ink2">{item.summary}</p>
      )}
    </a>
  )
}

function fmtDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

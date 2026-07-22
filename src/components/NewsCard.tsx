import { useState } from 'react'
import type { NewsItem } from '../lib/news'

/** One cited news item.
 *
 *  `full`   — the News tab's "top stories" grid card: image on top, then source
 *             + favicon + relative time, then the bold article headline.
 *  `compact`— the advisor chat's narrow row: text only, no lead image.
 *
 *  Either way the whole card is a single <a>: one tab stop, never nested
 *  interactives. Items without a URL never reach here (dropped server-side),
 *  and images/headlines come from the fetched page — never from the model. */
export default function NewsCard({
  item,
  variant = 'full',
}: {
  item: NewsItem
  variant?: 'compact' | 'full'
}) {
  const { label, days } = relativeDate(item.published)
  const stale = days > 60 // de-emphasize older-than-a-couple-months signal

  const shell =
    'group block rounded-card border border-line bg-raised transition-colors duration-150 hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface'

  const meta = (
    <div className="micro flex items-center gap-1.5 text-ink3">
      {item.favicon && <Img src={item.favicon} size={14} className="size-3.5 rounded-sm" />}
      <span className="truncate">{item.source}</span>
      {item.published && (
        <>
          <span aria-hidden>·</span>
          <time dateTime={item.published} className="shrink-0">
            {label}
          </time>
        </>
      )}
      <ExternalIcon />
    </div>
  )

  if (variant === 'compact') {
    return (
      <a
        {...linkProps(item)}
        className={`${shell} p-3 ${stale ? 'opacity-70' : ''}`}
      >
        {meta}
        <div className="mt-1.5 text-[13.5px] font-semibold leading-snug text-ink transition-colors duration-150 group-hover:text-accent group-visited:text-ink2">
          {item.title}
        </div>
      </a>
    )
  }

  return (
    <a
      {...linkProps(item)}
      className={`${shell} flex h-full flex-col overflow-hidden ${stale ? 'opacity-70' : ''}`}
    >
      <Lead item={item} />
      <div className="flex flex-1 flex-col p-3">
        {meta}
        <h3 className="mt-1.5 line-clamp-3 text-[14px] font-semibold leading-snug text-ink transition-colors duration-150 group-hover:text-accent group-visited:text-ink2">
          {item.title}
        </h3>
        {item.summary && (
          <p className="mt-1.5 line-clamp-2 text-[12.5px] leading-relaxed text-ink2">
            {item.summary}
          </p>
        )}
      </div>
    </a>
  )
}

function linkProps(item: NewsItem) {
  return {
    href: item.url,
    target: '_blank',
    rel: 'noopener noreferrer',
    'aria-label': `${item.title} — ${item.source}, opens in new tab`,
  } as const
}

/** The lead image: the real og:image, else the source favicon centered on a
 *  neutral tile, else no image band at all. Fixed 16:9 box reserved up front so
 *  a late-loading image never shifts the grid. Never a broken-image icon. */
function Lead({ item }: { item: NewsItem }) {
  const [failed, setFailed] = useState(false)
  const showImage = item.image && !failed
  if (!item.image && !item.favicon) return null

  return (
    <div className="relative aspect-[16/9] w-full shrink-0 overflow-hidden border-b border-line bg-surface">
      {showImage ? (
        <img
          src={item.image ?? undefined}
          alt=""
          width={480}
          height={270}
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
          className="size-full object-cover"
        />
      ) : item.favicon ? (
        <div className="grid size-full place-items-center">
          <Img src={item.favicon} size={28} className="size-7 rounded" />
        </div>
      ) : null}
    </div>
  )
}

/** An <img> that removes itself rather than showing a broken-image icon. */
function Img({ src, size, className }: { src: string; size: number; className: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return null
  return (
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={`shrink-0 ${className}`}
    />
  )
}

function ExternalIcon() {
  return (
    <svg
      width="11"
      height="11"
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden
      className="ml-auto shrink-0 text-ink3 transition-colors duration-150 group-hover:text-accent"
    >
      <path
        d="M4.5 2H10m0 0v5.5M10 2 2 10"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** Honest relative date + the age in days (for de-emphasis). */
function relativeDate(iso: string | null): { label: string; days: number } {
  if (!iso) return { label: '', days: 0 }
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return { label: iso, days: 0 }
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000)
  if (days <= 0) return { label: 'today', days: 0 }
  if (days === 1) return { label: 'yesterday', days }
  if (days < 7) return { label: `${days} days ago`, days }
  if (days < 30) return { label: `${Math.floor(days / 7)} wk ago`, days }
  if (days < 365) return { label: `${Math.floor(days / 30)} mo ago`, days }
  return { label: `${Math.floor(days / 365)} yr ago`, days }
}

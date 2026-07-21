import { useState } from 'react'
import type { NewsItem } from '../lib/news'

/** One cited news item — the shared atom for the News tab (`full`) and the
 *  advisor chat (`compact`). A single <a> wraps everything: one tab stop, even
 *  with the thumbnail. Google-News layout: headline + summary left, image right,
 *  source favicon by the source name. Items without a URL never reach here. */
export default function NewsCard({
  item,
  variant = 'full',
}: {
  item: NewsItem
  variant?: 'compact' | 'full'
}) {
  const { label, days } = relativeDate(item.published)
  const stale = days > 60 // de-emphasize older-than-a-couple-months signal

  return (
    <a
      href={item.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`${item.title} — ${item.source}, opens in new tab`}
      className={`group flex gap-3 rounded-card border border-line bg-raised p-3 transition-colors duration-150 hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface ${
        stale ? 'opacity-70' : ''
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="micro flex items-center gap-1.5 text-ink3">
          {item.favicon && <Favicon src={item.favicon} />}
          <span className="truncate">{item.source}</span>
          {item.published && (
            <>
              <span aria-hidden>·</span>
              <time dateTime={item.published} className="shrink-0">
                {label}
              </time>
            </>
          )}
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
        </div>

        <div className="mt-1.5 text-[13.5px] font-semibold leading-snug text-ink transition-colors duration-150 group-hover:text-accent group-visited:text-ink2">
          {item.title}
        </div>

        {variant === 'full' && item.summary && (
          <p className="mt-1.5 line-clamp-3 text-[12.5px] leading-relaxed text-ink2">
            {item.summary}
          </p>
        )}
      </div>

      {variant === 'full' && <Thumb item={item} />}
    </a>
  )
}

/** Thumbnail: the real og:image when present, else the source favicon on a
 *  neutral tile, else nothing (column dropped). Never a broken-image icon —
 *  a failed load falls back to the favicon tile, and a failed favicon hides. */
function Thumb({ item }: { item: NewsItem }) {
  const [imgFailed, setImgFailed] = useState(false)
  const showImage = item.image && !imgFailed

  if (!item.image && !item.favicon) return null

  return (
    <div className="hidden size-[76px] shrink-0 overflow-hidden rounded-lg border border-line bg-surface sm:block">
      {showImage ? (
        <img
          src={item.image ?? undefined}
          alt=""
          width={76}
          height={76}
          loading="lazy"
          decoding="async"
          onError={() => setImgFailed(true)}
          className="size-full object-cover"
        />
      ) : item.favicon ? (
        <div className="grid size-full place-items-center">
          <FaviconTile src={item.favicon} />
        </div>
      ) : null}
    </div>
  )
}

function Favicon({ src }: { src: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return null
  return (
    <img
      src={src}
      alt=""
      width={14}
      height={14}
      loading="lazy"
      onError={() => setFailed(true)}
      className="size-3.5 shrink-0 rounded-sm"
    />
  )
}

function FaviconTile({ src }: { src: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return null
  return (
    <img
      src={src}
      alt=""
      width={24}
      height={24}
      loading="lazy"
      onError={() => setFailed(true)}
      className="size-6 rounded"
    />
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

/** News transport. GETs the per-family digest from the advisor backend
 *  (NEWS_TAB.md §2/§6). The base URL is derived from VITE_AGENT_URL — one env
 *  var, one backend. No mock fallback: without an endpoint the tab shows its
 *  error state honestly instead of fabricated headlines. */

import type { Family } from '../types'

const AGENT_URL = import.meta.env.VITE_AGENT_URL

export const newsIsLive = Boolean(AGENT_URL)

export interface NewsItem {
  title: string
  source: string
  url: string
  published: string | null
  summary: string
}

export interface NewsFeed {
  family: string
  fetched_at: string
  items: NewsItem[]
}

export async function fetchNews(family: Family, signal?: AbortSignal): Promise<NewsFeed> {
  if (!AGENT_URL) throw new Error('no advisor endpoint is configured (VITE_AGENT_URL)')
  const base = new URL(AGENT_URL).origin
  const res = await fetch(`${base}/api/v1/news?family=${encodeURIComponent(family)}`, { signal })
  if (!res.ok) throw new Error(`News responded ${res.status}`)
  return (await res.json()) as NewsFeed
}

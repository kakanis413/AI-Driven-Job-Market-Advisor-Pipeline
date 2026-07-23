import { useCallback, useEffect, useState } from 'react'

/** Tiny hash router — no router dependency.
 *  `#/` → landing, `#/explore` → explorer, `#/explore/heatmap` → explorer in
 *  grid view, `#/news/STEM` → news tab preselected to a family, `#/chat` → the
 *  advisor home (`#/chat/11.0701` pre-selects a major by CIP). */

export type Page = 'landing' | 'explore' | 'news' | 'chat'

function parse(): { page: Page; sub: string | null } {
  const [p, sub] = location.hash.replace(/^#\/?/, '').split('/')
  if (p === 'explore' || p === 'news' || p === 'chat') {
    return { page: p, sub: sub ? decodeURIComponent(sub) : null }
  }
  return { page: 'landing', sub: null }
}

export function useRoute() {
  const [route, setRoute] = useState(parse)

  useEffect(() => {
    const onChange = () => setRoute(parse())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const nav = useCallback((page: Page, sub?: string) => {
    location.hash =
      page === 'landing' ? '/' : `/${page}${sub ? `/${encodeURIComponent(sub)}` : ''}`
    window.scrollTo({ top: 0 })
  }, [])

  return { ...route, nav }
}

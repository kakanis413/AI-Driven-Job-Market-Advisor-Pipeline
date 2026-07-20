import { useCallback, useEffect, useState } from 'react'

/** Tiny hash router — three pages, no router dependency.
 *  `#/` → landing, `#/explore` → explorer, `#/explore/heatmap` → explorer in
 *  grid view, `#/news/STEM` → news tab preselected to a family. */

export type Page = 'landing' | 'explore' | 'news'

function parse(): { page: Page; sub: string | null } {
  const [p, sub] = location.hash.replace(/^#\/?/, '').split('/')
  if (p === 'explore' || p === 'news') {
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

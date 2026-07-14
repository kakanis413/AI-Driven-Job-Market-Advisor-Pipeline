import { useCallback, useEffect, useState } from 'react'

/** Tiny hash router — two pages, no router dependency.
 *  `#/` → landing, `#/explore` → explorer, `#/explore/heatmap` → explorer in grid view. */

export type Page = 'landing' | 'explore'

function parse(): { page: Page; sub: string | null } {
  const [p, sub] = location.hash.replace(/^#\/?/, '').split('/')
  return p === 'explore' ? { page: 'explore', sub: sub || null } : { page: 'landing', sub: null }
}

export function useRoute() {
  const [route, setRoute] = useState(parse)

  useEffect(() => {
    const onChange = () => setRoute(parse())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])

  const nav = useCallback((page: Page, sub?: string) => {
    location.hash = page === 'explore' ? `/explore${sub ? `/${sub}` : ''}` : '/'
    window.scrollTo({ top: 0 })
  }, [])

  return { ...route, nav }
}

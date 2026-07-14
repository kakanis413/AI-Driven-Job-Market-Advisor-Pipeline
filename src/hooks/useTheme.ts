import { useEffect, useState } from 'react'
import type { Mode } from '../design/tokens'

/** Theme is applied to <html> before first paint by the inline script in
 *  index.html; this hook takes over from there and persists changes. */
export function useTheme() {
  const [mode, setMode] = useState<Mode>(() =>
    document.documentElement.classList.contains('dark') ? 'dark' : 'light',
  )

  useEffect(() => {
    document.documentElement.classList.toggle('dark', mode === 'dark')
    localStorage.setItem('mv-theme', mode)
  }, [mode])

  return { mode, toggle: () => setMode((m) => (m === 'dark' ? 'light' : 'dark')) }
}

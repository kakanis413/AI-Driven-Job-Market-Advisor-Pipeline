import { useCallback, useEffect, useState } from 'react'
import type { Major } from '../types'

const DATA_URL = import.meta.env.VITE_DATA_URL || '/data.json'

type State =
  | { status: 'loading'; majors: Major[] }
  | { status: 'error'; majors: Major[]; error: string }
  | { status: 'ready'; majors: Major[] }

function isMajor(r: unknown): r is Major {
  if (typeof r !== 'object' || r === null) return false
  const m = r as Record<string, unknown>
  return (
    typeof m.cip === 'string' &&
    typeof m.major === 'string' &&
    typeof m.family === 'string' &&
    typeof m.completions === 'number' &&
    typeof m.exposure === 'number' &&
    m.exposure >= 0 &&
    m.exposure <= 10 &&
    (typeof m.median_pay === 'number' || m.median_pay === null) &&
    (typeof m.growth === 'string' || m.growth === null) &&
    Array.isArray(m.occupations) &&
    typeof m.rationale === 'string'
  )
}

export function useMajors() {
  const [state, setState] = useState<State>({ status: 'loading', majors: [] })

  const load = useCallback(async () => {
    setState({ status: 'loading', majors: [] })
    try {
      const res = await fetch(DATA_URL)
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const json: unknown = await res.json()
      if (!Array.isArray(json)) throw new Error('expected a JSON array of majors')
      const majors = json.filter(isMajor)
      const dropped = json.length - majors.length
      if (dropped > 0) console.warn(`useMajors: dropped ${dropped} invalid row(s)`)
      if (majors.length === 0) throw new Error('no valid rows in data')
      setState({ status: 'ready', majors })
    } catch (e) {
      setState({
        status: 'error',
        majors: [],
        error: e instanceof Error ? e.message : String(e),
      })
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return { ...state, url: DATA_URL, retry: load }
}

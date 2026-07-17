import { useCallback, useEffect, useState } from 'react'
import type { Major } from '../types'
import { normalizeMajors } from '../lib/normalizeMajors'

const DATA_URL = import.meta.env.VITE_DATA_URL || '/data.json'

type State =
  | { status: 'loading'; majors: Major[] }
  | { status: 'error'; majors: Major[]; error: string }
  | { status: 'ready'; majors: Major[] }

export function useMajors() {
  const [state, setState] = useState<State>({ status: 'loading', majors: [] })

  const load = useCallback(async () => {
    setState({ status: 'loading', majors: [] })
    try {
      const res = await fetch(DATA_URL)
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const json: unknown = await res.json()
      const majors = normalizeMajors(json)
      const dropped = (json as unknown[]).length - majors.length
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

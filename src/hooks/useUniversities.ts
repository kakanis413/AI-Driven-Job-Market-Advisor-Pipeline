import { useEffect, useState } from 'react'

/** One US university row from /universities.json (built from the IPEDS HD
 *  directory by scripts/build_universities.py). Filtered client-side by the
 *  picker — there is no network call to validate a school. */
export interface University {
  unitid: number
  name: string
  state: string
  domain: string
}

const URL = '/universities.json'

// Module-level cache so the list is fetched once and shared (mirrors useMajors'
// intent, but the directory never changes within a session).
let cache: University[] | null = null
let inflight: Promise<University[]> | null = null

function isRow(x: unknown): x is University {
  if (typeof x !== 'object' || x === null) return false
  const o = x as Record<string, unknown>
  return (
    typeof o.unitid === 'number' &&
    typeof o.name === 'string' &&
    typeof o.domain === 'string' &&
    typeof o.state === 'string'
  )
}

async function fetchUniversities(): Promise<University[]> {
  if (cache) return cache
  if (!inflight) {
    inflight = fetch(URL)
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
        return res.json() as Promise<unknown>
      })
      .then((json) => {
        const rows = Array.isArray(json) ? json.filter(isRow) : []
        cache = rows
        return rows
      })
      .catch((e) => {
        inflight = null // allow a retry on next mount
        throw e
      })
  }
  return inflight
}

type Status = 'loading' | 'ready' | 'error'

export function useUniversities() {
  const [universities, setUniversities] = useState<University[]>(cache ?? [])
  const [status, setStatus] = useState<Status>(cache ? 'ready' : 'loading')

  useEffect(() => {
    if (cache) return
    let live = true
    fetchUniversities()
      .then((rows) => {
        if (!live) return
        setUniversities(rows)
        setStatus('ready')
      })
      .catch(() => {
        if (!live) return
        setStatus('error')
      })
    return () => {
      live = false
    }
  }, [])

  return { universities, status }
}

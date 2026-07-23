import { useSyncExternalStore } from 'react'

/** The student's chosen school + intended major. One shared source, so the
 *  Explore advisor panel and the /chat page personalize identically — the school
 *  is set once and used everywhere. Persisted to localStorage (like the theme). */
export interface UniversityContext {
  unitid: number
  name: string
  domain: string
  intendedMajor: string
}

interface Store {
  university: UniversityContext | null
  /** The soft gate was dismissed once → never nag again. */
  gateDismissed: boolean
  /** The student has sent at least one advisor message → the gate is once-per-user. */
  hasChatted: boolean
}

const KEY = 'mv-university'
const KEY_GATE = 'mv-gate-dismissed'
const KEY_CHATTED = 'mv-has-chatted'

function load(): Store {
  let university: UniversityContext | null = null
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const p = JSON.parse(raw) as Partial<UniversityContext>
      if (typeof p.unitid === 'number' && typeof p.name === 'string' && typeof p.domain === 'string') {
        university = {
          unitid: p.unitid,
          name: p.name,
          domain: p.domain,
          intendedMajor: typeof p.intendedMajor === 'string' ? p.intendedMajor : '',
        }
      }
    }
  } catch {
    university = null
  }
  return {
    university,
    gateDismissed: localStorage.getItem(KEY_GATE) === '1',
    hasChatted: localStorage.getItem(KEY_CHATTED) === '1',
  }
}

// Module-level store shared by every consumer; useSyncExternalStore keeps them
// all in sync when any one of them mutates it.
let store: Store = load()
const listeners = new Set<() => void>()

function emit() {
  for (const l of listeners) l()
}
function set(next: Partial<Store>) {
  store = { ...store, ...next }
  emit()
}
function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => listeners.delete(cb)
}
function getSnapshot(): Store {
  return store
}

export function useUniversity() {
  const s = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)

  const setUniversity = (u: UniversityContext) => {
    try {
      localStorage.setItem(KEY, JSON.stringify(u))
    } catch {
      /* storage may be unavailable (private mode) — keep the in-memory value */
    }
    set({ university: u })
  }
  const clearUniversity = () => {
    try {
      localStorage.removeItem(KEY)
    } catch {
      /* ignore */
    }
    set({ university: null })
  }
  const dismissGate = () => {
    try {
      localStorage.setItem(KEY_GATE, '1')
    } catch {
      /* ignore */
    }
    set({ gateDismissed: true })
  }
  const markChatted = () => {
    if (store.hasChatted) return
    try {
      localStorage.setItem(KEY_CHATTED, '1')
    } catch {
      /* ignore */
    }
    set({ hasChatted: true })
  }

  return {
    university: s.university,
    gateDismissed: s.gateDismissed,
    hasChatted: s.hasChatted,
    setUniversity,
    clearUniversity,
    dismissGate,
    markChatted,
  }
}

/** Advisor transport. POSTs the student's message — plus the selected major's
 *  record when there is one — to VITE_AGENT_URL (the FastAPI
 *  /api/v1/analyze-major endpoint).
 *
 *  With no major selected the question still goes to the agent, which answers in
 *  general mode (conceptual, no invented numbers). The mock echo now stands in
 *  ONLY when the endpoint itself is unset, labeled "offline preview" so it is
 *  never mistaken for a real advisor. */

import type { Major } from '../types'

const AGENT_URL = import.meta.env.VITE_AGENT_URL

/** The SSE twin of AGENT_URL. Derived rather than configured so an existing
 *  deployment picks up streaming without a second env var; set
 *  VITE_AGENT_STREAM_URL to override when the routes don't share a prefix. */
const STREAM_URL: string | undefined =
  import.meta.env.VITE_AGENT_STREAM_URL ||
  (AGENT_URL ? `${String(AGENT_URL).replace(/\/+$/, '')}/stream` : undefined)

export const advisorIsLive = Boolean(AGENT_URL)

/** Sent as `X-API-Key` when the backend has `ADVISOR_API_KEY` set. Unset → the
 *  header is omitted and requests are byte-for-byte what they were before.
 *
 *  Note this is a *public* value: anything in a Vite bundle ships to the browser and
 *  is readable by anyone who opens devtools. It raises the bar against casual abuse
 *  of an endpoint that spends money per request; it is not a secret, and it is not a
 *  substitute for real auth (IAP, a gateway, signed sessions) in front of Cloud Run. */
const API_KEY: string | undefined = import.meta.env.VITE_ADVISOR_API_KEY

const jsonHeaders = (): Record<string, string> => ({
  'Content-Type': 'application/json',
  ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
})

export interface AdvisorPayload {
  major: Major | null
  message: string
  /** Optional "personalize for my school" layer. When present, the backend runs
   *  one domain-scoped program search and layers school-specific guidance on top
   *  of the national data. Absent → the request is byte-for-byte the national one. */
  university?: string
  universityDomain?: string
  intendedMajor?: string
  /** Called with each chunk as it arrives. Supplying it opts into the SSE route:
   *  time-to-first-token drops from whole-answer latency (~9s) to ~1s. Omit it and
   *  the blocking JSON route is used, unchanged. */
  onToken?: (chunk: string) => void
  /** Named hop the backend is currently running ("Searching recent news…"). A turn
   *  that calls a slow tool emits no token for seconds; this is what fills that gap
   *  with something true. */
  onStatus?: (label: string) => void
  signal?: AbortSignal
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** The FastAPI AdvisorRequest body. With no major selected we send the question
 *  alone; `major_name` is optional and the backend switches to general mode. */
function buildBody({
  major,
  message,
  university,
  universityDomain,
  intendedMajor,
}: AdvisorPayload): Record<string, unknown> {
  const base = major
    ? {
        major_name: major.major,
        cip: major.cip || null,
        exposure: major.exposure,
        // Send real nulls. The backend schema accepts null for both, and reports
        // them to the agent as "not available" — coercing to 0 / a string would
        // tell the advisor pay is literally $0, which is a grounding bug.
        median_pay: major.median_pay,
        growth: major.growth,
        occupations: major.occupations.map((o) => ({
          soc: o.soc,
          title: o.title,
          exposure: o.exposure,
        })),
        rationale: major.rationale || null,
        query_context: message,
      }
    : { query_context: message }

  // Only fold in the school when one is set, so with no school the body is
  // byte-for-byte today's request (backward compatible; same backend cache key).
  return university && universityDomain
    ? {
        ...base,
        university,
        university_domain: universityDomain,
        intended_major: intendedMajor,
      }
    : base
}

function offlineEcho({ major, message, university }: AdvisorPayload): string {
  const who = major ? `${major.major} (CIP ${major.cip})` : 'your question'
  const school = university ? ` for ${university}` : ''
  return `Offline preview — no advisor endpoint is configured (VITE_AGENT_URL). Echoing ${who}${school}: “${message}”.`
}

/** Read one SSE event block into its name and JSON payload. The backend
 *  JSON-encodes the payload because advisor answers are markdown, and a bare
 *  newline in a `data:` field would end the event and truncate the reply. */
function parseEvent(block: string): { name: string; data: Record<string, unknown> } | null {
  let name = 'message'
  let raw: string | null = null
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) name = line.slice(7)
    else if (line.startsWith('data: ')) raw = line.slice(6)
  }
  if (raw === null) return null
  try {
    const data: unknown = JSON.parse(raw)
    return { name, data: typeof data === 'object' && data !== null ? (data as Record<string, unknown>) : {} }
  } catch {
    return null
  }
}

/** Streams the answer, invoking `onToken` per chunk, and resolves with the full
 *  text. Throws on a terminal `error` event — whatever streamed before the throw
 *  is already on screen, so the panel keeps it and appends the error state. */
async function streamAdvisor(payload: AdvisorPayload, url: string): Promise<string> {
  const res = await fetch(url, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(buildBody(payload)),
    signal: payload.signal,
  })
  if (!res.ok) throw new Error(`Advisor responded ${res.status}`)
  if (!res.body) throw new Error('Advisor returned no stream')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let full = ''
  let failure: Error | null = null

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // Events are \n\n-delimited; the trailing fragment is an incomplete event.
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''

    for (const block of blocks) {
      if (!block.trim()) continue
      const evt = parseEvent(block)
      if (!evt) continue
      if (evt.name === 'token' && typeof evt.data.text === 'string') {
        full += evt.data.text
        payload.onToken?.(evt.data.text)
      } else if (evt.name === 'status' && typeof evt.data.label === 'string') {
        payload.onStatus?.(evt.data.label)
      } else if (evt.name === 'error') {
        failure = new Error(
          typeof evt.data.error === 'string' && evt.data.error
            ? evt.data.error
            : 'the advisor stream failed',
        )
      }
    }
  }

  if (failure) throw failure
  if (!full.trim()) throw new Error('Advisor returned an empty response')
  return full
}

export async function askAdvisor(payload: AdvisorPayload): Promise<string> {
  const { onToken } = payload

  // Offline preview ONLY when there is no endpoint to call.
  if (!AGENT_URL) {
    await wait(700)
    const echo = offlineEcho(payload)
    onToken?.(echo)
    return echo
  }

  // Streaming is opt-in per call: no onToken → the blocking route, unchanged.
  if (onToken && STREAM_URL) {
    try {
      return await streamAdvisor(payload, STREAM_URL)
    } catch (err) {
      // A 404 means the deployed backend predates /stream, not that the advisor
      // is down. Fall back once to the blocking route rather than showing an
      // error state for a backend that answers fine.
      if (err instanceof Error && err.message.includes('404')) {
        return askAdvisor({ ...payload, onToken: undefined })
      }
      throw err
    }
  }

  const res = await fetch(AGENT_URL, {
    method: 'POST',
    headers: jsonHeaders(),
    body: JSON.stringify(buildBody(payload)),
    signal: payload.signal,
  })
  if (!res.ok) throw new Error(`Advisor responded ${res.status}`)

  // Backend returns { agent_node, status, generated_guidance }. Keep
  // reply/message fallbacks so a plainer endpoint still works; surface a
  // returned error string as a thrown error for the panel's error state.
  const text = await res.text()
  let json: unknown
  try {
    json = JSON.parse(text)
  } catch {
    return text // plain-text body
  }
  if (typeof json === 'object' && json !== null) {
    const o = json as Record<string, unknown>
    if (typeof o.generated_guidance === 'string' && o.generated_guidance) {
      return o.generated_guidance
    }
    if (typeof o.reply === 'string') return o.reply
    if (typeof o.message === 'string') return o.message
    if (typeof o.error === 'string' && o.error) throw new Error(o.error)
  }
  return text
}

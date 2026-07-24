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

export const advisorIsLive = Boolean(AGENT_URL)

export interface AdvisorPayload {
  major: Major | null
  message: string
  /** Optional "personalize for my school" layer. When present, the backend runs
   *  one domain-scoped program search and layers school-specific guidance on top
   *  of the national data. Absent → the request is byte-for-byte the national one. */
  university?: string
  universityDomain?: string
  intendedMajor?: string
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

export async function askAdvisor({
  major,
  message,
  university,
  universityDomain,
  intendedMajor,
}: AdvisorPayload): Promise<string> {
  // Offline preview ONLY when there is no endpoint to call.
  if (!AGENT_URL) {
    await wait(700)
    const who = major ? `${major.major} (CIP ${major.cip})` : 'your question'
    const school = university ? ` for ${university}` : ''
    return `Offline preview — no advisor endpoint is configured (VITE_AGENT_URL). Echoing ${who}${school}: “${message}”.`
  }

  // Body matches the FastAPI AdvisorRequest (/api/v1/analyze-major). With no
  // major selected we send the question alone; `major_name` is optional and the
  // backend switches to general mode.
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
        query_context: message,
      }
    : { query_context: message }

  // Only fold in the school when one is set, so with no school the body is
  // byte-for-byte today's request (backward compatible; same backend cache key).
  const body =
    university && universityDomain
      ? {
          ...base,
          university,
          university_domain: universityDomain,
          intended_major: intendedMajor,
        }
      : base

  const res = await fetch(AGENT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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

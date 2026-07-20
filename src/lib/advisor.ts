/** Advisor transport. POSTs the selected major's record + the student's message
 *  to VITE_AGENT_URL (the FastAPI /api/v1/analyze-major endpoint). When the env
 *  var is unset — or no major is selected to ground on — a mock echo handler
 *  stands in, labeled "offline preview" so it is never mistaken for a real
 *  advisor. */

import type { Major } from '../types'

const AGENT_URL = import.meta.env.VITE_AGENT_URL

export const advisorIsLive = Boolean(AGENT_URL)

export interface AdvisorPayload {
  major: Major | null
  message: string
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

export async function askAdvisor({ major, message }: AdvisorPayload): Promise<string> {
  // Offline preview: no endpoint configured, or no major selected to ground on.
  if (!AGENT_URL || !major) {
    await wait(700)
    const reason = !AGENT_URL
      ? 'no advisor endpoint is configured (VITE_AGENT_URL)'
      : 'select a major to get grounded answers'
    const who = major ? `${major.major} (CIP ${major.cip})` : 'your selection'
    return `Offline preview — ${reason}. Echoing your question about ${who}: “${message}”.`
  }

  // Body matches the FastAPI MajorAnalysisSchema (/api/v1/analyze-major).
  const body = {
    major_name: major.major,
    cip: major.cip || null,
    exposure: major.exposure,
    // Send real nulls. The backend schema accepts null for both, and reports them
    // to the agent as "not available" — coercing to 0 / a string would tell the
    // advisor pay is literally $0, which is a grounding bug.
    median_pay: major.median_pay,
    growth: major.growth,
    occupations: major.occupations.map((o) => ({
      soc: o.soc,
      title: o.title,
      exposure: o.exposure,
    })),
    query_context: message,
  }

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

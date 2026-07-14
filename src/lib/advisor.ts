/** Advisor transport. POSTs {major, cip, message} to VITE_AGENT_URL; when the
 *  env var is unset, a mock echo handler stands in (labeled "offline preview"
 *  in the UI so it is never mistaken for a real advisor). */

const AGENT_URL = import.meta.env.VITE_AGENT_URL

export const advisorIsLive = Boolean(AGENT_URL)

export interface AdvisorPayload {
  major: string
  cip: string
  message: string
}

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

export async function askAdvisor(payload: AdvisorPayload): Promise<string> {
  if (!AGENT_URL) {
    await wait(700)
    return (
      `Offline preview — no advisor endpoint is configured (VITE_AGENT_URL). ` +
      `Echoing your question about ${payload.major} (CIP ${payload.cip}): ` +
      `“${payload.message}”. Point VITE_AGENT_URL at a real agent to get grounded answers here.`
    )
  }

  const res = await fetch(AGENT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`Advisor responded ${res.status}`)

  // Accept {reply: string}, {message: string}, or a plain-text body.
  const text = await res.text()
  try {
    const json: unknown = JSON.parse(text)
    if (typeof json === 'object' && json !== null) {
      const o = json as Record<string, unknown>
      if (typeof o.reply === 'string') return o.reply
      if (typeof o.message === 'string') return o.message
    }
  } catch {
    /* plain text */
  }
  return text
}

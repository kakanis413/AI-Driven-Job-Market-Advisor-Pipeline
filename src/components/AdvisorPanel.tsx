import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { fmtExposure } from '../design/scales'
import { askAdvisor } from '../lib/advisor'
import type { Major } from '../types'

interface Msg {
  id: number
  role: 'user' | 'advisor' | 'error'
  text: string
}

/** Advisor chat, pre-seeded with the selected major (or generic when none).
 *  Remounted per major via key in Explore, so state resets naturally. */
export default function AdvisorPanel({ major }: { major: Major | null }) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState(
    major
      ? `What does an AI exposure of ${fmtExposure(major.exposure)}/10 mean for ${major.major}?`
      : 'Which majors are most exposed to AI?',
  )
  const [pending, setPending] = useState(false)
  const idRef = useRef(0)
  const lastSentRef = useRef('')
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, pending])

  const push = (role: Msg['role'], text: string) =>
    setMessages((ms) => [...ms, { id: idRef.current++, role, text }])

  const send = (raw: string) => {
    const text = raw.trim()
    if (!text || pending) return
    lastSentRef.current = text
    push('user', text)
    setInput('')
    setPending(true)
    askAdvisor({ major: major?.major ?? 'General', cip: major?.cip ?? '—', message: text })
      .then((reply) => push('advisor', reply))
      .catch((e: unknown) =>
        push('error', `Couldn’t reach the advisor (${e instanceof Error ? e.message : String(e)}).`),
      )
      .finally(() => setPending(false))
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={logRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3" aria-live="polite">
        {messages.length === 0 && (
          <div className="rounded-card border border-dashed border-line p-3 text-[12.5px] leading-relaxed text-ink2">
            {major ? (
              <>
                Exploring <b className="font-semibold text-ink">{major.major}</b>. Send the drafted
                question below, or try:
              </>
            ) : (
              <>Pick a major on the map for grounded context — or ask anything. Try:</>
            )}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(major
                ? ['Which skills stay valuable here?', 'What adjacent majors are less exposed?']
                : ['Which majors are least exposed?', 'How is exposure scored?']
              ).map(
                (s) => (
                  <button
                    key={s}
                    onClick={() => setInput(s)}
                    className="rounded-full border border-line bg-raised px-2.5 py-1 text-[12px] text-ink2 hover:border-accent hover:text-ink"
                  >
                    {s}
                  </button>
                ),
              )}
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`max-w-[88%] rounded-2xl px-3.5 py-2 text-[13.5px] leading-relaxed ${
              msg.role === 'user'
                ? 'ml-auto rounded-br-md bg-ink text-page'
                : msg.role === 'advisor'
                  ? 'mr-auto rounded-bl-md border border-line bg-raised text-ink'
                  : 'mr-auto rounded-bl-md border border-line bg-raised text-ink2'
            }`}
          >
            {msg.text}
            {msg.role === 'error' && (
              <button
                onClick={() => send(lastSentRef.current)}
                className="mt-1.5 block text-[12.5px] font-semibold text-accent hover:underline"
              >
                Retry
              </button>
            )}
          </div>
        ))}
        {pending && (
          <div className="mr-auto flex w-14 items-center justify-center gap-1 rounded-2xl rounded-bl-md border border-line bg-raised px-3.5 py-3">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="size-1.5 rounded-full bg-ink3"
                animate={{ opacity: [0.25, 1, 0.25] }}
                transition={{ repeat: Infinity, duration: 1.1, delay: i * 0.18 }}
              />
            ))}
          </div>
        )}
      </div>

      <form
        className="flex gap-2 border-t border-line p-3"
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
      >
        <input
          className="h-10 min-w-0 flex-1 rounded-[10px] border border-line bg-raised px-3 text-[13.5px] text-ink outline-none placeholder:text-ink3 focus:border-accent"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={major ? `Ask about ${major.major}…` : 'Ask the advisor…'}
          aria-label="Message the advisor"
        />
        <button
          type="submit"
          disabled={pending || !input.trim()}
          aria-label="Send message"
          className="grid size-10 shrink-0 place-items-center rounded-[10px] bg-ink text-page transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
            <path
              d="M7.5 12.5v-10m0 0L3 7m4.5-4.5L12 7"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </form>
    </div>
  )
}

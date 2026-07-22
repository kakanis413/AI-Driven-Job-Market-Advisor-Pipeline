import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { fmtExposure, fmtPay, growthOf } from '../design/scales'
import { askAdvisor } from '../lib/advisor'
import type { Major } from '../types'

interface Msg {
  id: number
  role: 'user' | 'advisor' | 'error'
  text: string
}

/** Staged status text for the ~11s multi-agent round trip: rotate through what
 *  the backend is plausibly doing, and after 5s add an elapsed hint so a long
 *  wait reads as working, not frozen. Timing is presentational only — it does
 *  not observe the real agent route. */
const THINKING_STAGES = [
  'Checking the data…',
  'Looking up occupations…',
  'Writing your guidance…',
] as const
const STAGE_MS = 3500
const ELAPSED_HINT_AFTER_S = 5

function ThinkingIndicator() {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(t)
  }, [])

  const stage =
    THINKING_STAGES[
      Math.min(Math.floor((seconds * 1000) / STAGE_MS), THINKING_STAGES.length - 1)
    ]

  return (
    <div className="mr-auto flex items-center gap-2 rounded-2xl rounded-bl-md border border-line bg-raised px-3.5 py-2.5">
      <span className="flex items-center gap-1" aria-hidden>
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="size-1.5 rounded-full bg-ink3"
            animate={{ opacity: [0.25, 1, 0.25] }}
            transition={{ repeat: Infinity, duration: 1.1, delay: i * 0.18 }}
          />
        ))}
      </span>
      <span className="text-[12.5px] text-ink2" role="status">
        {stage}
        {seconds >= ELAPSED_HINT_AFTER_S && (
          <span className="text-ink3"> · {seconds}s</span>
        )}
      </span>
    </div>
  )
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

  // Soft fade masks at whichever edge has hidden content, so overflow is never
  // silent. Recomputed on scroll and whenever the thread changes.
  const [fade, setFade] = useState({ top: false, bottom: false })
  const onScroll = () => {
    const el = logRef.current
    if (!el) return
    setFade({
      top: el.scrollTop > 8,
      bottom: el.scrollTop + el.clientHeight < el.scrollHeight - 8,
    })
  }
  const maskImage = `linear-gradient(to bottom, ${
    fade.top ? 'transparent, #000 22px' : '#000 0'
  }, ${fade.bottom ? '#000 calc(100% - 22px), transparent' : '#000 100%'})`

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
    onScroll()
  }, [messages, pending])

  const started = messages.length > 0

  const push = (role: Msg['role'], text: string) =>
    setMessages((ms) => [...ms, { id: idRef.current++, role, text }])

  const send = (raw: string) => {
    const text = raw.trim()
    if (!text || pending) return
    lastSentRef.current = text
    push('user', text)
    setInput('')
    setPending(true)
    askAdvisor({ major: major ?? null, message: text })
      .then((reply) => push('advisor', reply))
      .catch((e: unknown) =>
        push('error', `Couldn’t reach the advisor (${e instanceof Error ? e.message : String(e)}).`),
      )
      .finally(() => setPending(false))
  }

  const answered = major && messages.some((m) => m.role === 'advisor')

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        ref={logRef}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-3"
        aria-live="polite"
        style={{ WebkitMaskImage: maskImage, maskImage }}
      >
        {/* Bottom-anchored thread */}
        <div className="flex min-h-full flex-col justify-end gap-3">
          {!started && (
            <div className="text-[12.5px] leading-relaxed text-ink3">
              {major ? (
                <>
                  Exploring <b className="font-semibold text-ink">{major.major}</b>. Send the drafted
                  question, or pick a suggestion below.
                </>
              ) : (
                <>Pick a major on the map for grounded context — or ask anything below.</>
              )}
            </div>
          )}
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-[13.5px] leading-relaxed ${
                msg.role === 'user'
                  ? 'ml-auto rounded-br-md bg-ink text-page'
                  : msg.role === 'advisor'
                    ? 'mr-auto rounded-bl-md border border-line bg-raised text-ink'
                    : 'mr-auto rounded-bl-md border border-line bg-raised text-ink2'
              }`}
            >
              {msg.role === 'advisor' ? (
                <div className="prose prose-invert max-w-none space-y-2 [&>p]:m-0 [&>ul]:my-1.5 [&>ul]:list-disc [&>ul]:pl-4 [&>ol]:list-decimal [&>ol]:pl-4 [&_strong]:font-semibold [&_h3]:my-1 [&_h3]:text-[14px] [&_h3]:font-semibold">
                  <ReactMarkdown>{msg.text}</ReactMarkdown>
                </div>
              ) : (
                <span>{msg.text}</span>
              )}

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
          {pending && <ThinkingIndicator />}
          
          {/* Grounded stat strip */}
          {answered && (
            <div className="grid grid-cols-3 overflow-hidden rounded-xl border border-line">
              <StatCell label="Exposure" value={`${fmtExposure(major.exposure)} / 10`} />
              <StatCell label="Median pay" value={fmtPay(major.median_pay)} divider />
              <StatCell label="Growth" value={growthOf(major.growth).label} divider />
            </div>
          )}

          {/* Hand-off to News tab */}
          {answered && (
            <a
              href={`#/news/${encodeURIComponent(major.family)}`}
              className="text-[12.5px] font-semibold text-accent hover:underline"
            >
              More news for {major.family} →
            </a>
          )}
        </div>
      </div>

      {/* Suggestions */}
      {!started && (
        <div className="flex flex-wrap gap-1.5 px-3 pt-2">
          {(major
            ? ['Which skills stay valuable here?', 'What adjacent majors are less exposed?']
            : ['Which majors are least exposed?', 'How is exposure scored?']
          ).map((s) => (
            <button
              key={s}
              onClick={() => setInput(s)}
              className="rounded-full border border-line bg-transparent px-3 py-1 text-[12px] text-ink2 transition-colors hover:border-accent hover:text-ink"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="flex gap-2 p-3"
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

/** One cell of the grounded stat strip under an advisor reply. */
function StatCell({
  label,
  value,
  divider,
}: {
  label: string
  value: string
  divider?: boolean
}) {
  return (
    <div className={`bg-raised px-2.5 py-1.5 ${divider ? 'border-l border-line' : ''}`}>
      <div className="micro text-ink3">{label}</div>
      <div className="mt-0.5 text-[13px] font-semibold text-ink" style={{ fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </div>
    </div>
  )
}
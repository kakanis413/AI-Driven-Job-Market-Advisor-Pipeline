import { useMemo, useState } from 'react'
import AdvisorPanel from '../components/AdvisorPanel'
import MajorDetailCard from '../components/MajorDetailCard'
import SearchSpotlight from '../components/SearchSpotlight'
import UniversityGateModal from '../components/UniversityGateModal'
import { normalize } from '../design/scales'
import { EXPOSURE_STOPS, type Mode } from '../design/tokens'
import { useRoute } from '../hooks/useRoute'
import { useUniversity } from '../hooks/useUniversity'
import type { Major } from '../types'

// The school chip's violet — existing exposure-ramp stops, not a new token.
const CHIP_FILL = EXPOSURE_STOPS.light[0]
const CHIP_INK = EXPOSURE_STOPS.light[4]

interface Props {
  majors: Major[]
  mode: Mode
  /** Optional CIP from the route (#/chat/11.07) to pre-select a major. */
  initialCip?: string | null
}

/** The roomy advisor home. Coexists with the Explore floating panel (that quick
 *  panel stays). A context rail shows the selected major's NATIONAL estimates;
 *  the chat itself reuses AdvisorPanel and stays fully usable with no school.
 *  A major can be pinned right here (inline search) — no trip to the map — and
 *  the school's intended major offers a one-click pin so personalization feeds
 *  the grounded rail. */
export default function Chat({ majors, mode, initialCip }: Props) {
  const { nav } = useRoute()
  const { university, clearUniversity } = useUniversity()
  const [gateOpen, setGateOpen] = useState(false)
  const [pickQuery, setPickQuery] = useState('')

  const selected = useMemo(
    () => (initialCip ? majors.find((m) => m.cip === initialCip) ?? null : null),
    [majors, initialCip],
  )

  // The major that matches the school's intended major (by name) — offered as a
  // one-click pin so "ASU · computer science" can ground the rail in one tap.
  const intendedMatch = useMemo(() => {
    const q = normalize(university?.intendedMajor ?? '')
    if (!q) return null
    return (
      majors.find((m) => normalize(m.major) === q) ??
      majors.find((m) => normalize(m.major).includes(q) || q.includes(normalize(m.major))) ??
      null
    )
  }, [majors, university])

  const pinMajor = (m: Major) => nav('chat', m.cip)

  return (
    <div className="mx-auto max-w-[1200px] px-5 pb-24 pt-6 md:px-8">
      {/* School chip (or an invitation to add one). The chat below works either way. */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        {university ? (
          <span
            className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13px] font-medium"
            style={{ background: CHIP_FILL, color: CHIP_INK, borderColor: CHIP_INK }}
          >
            <span className="truncate">
              {university.name}
              {university.intendedMajor ? ` · ${university.intendedMajor}` : ''}
            </span>
            <button
              onClick={clearUniversity}
              aria-label={`Remove ${university.name}`}
              className="grid size-4 place-items-center rounded-full transition-opacity hover:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              style={{ color: CHIP_INK }}
            >
              <svg width="9" height="9" viewBox="0 0 13 13" fill="none" aria-hidden>
                <path d="M2 2l9 9M11 2l-9 9" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
              </svg>
            </button>
          </span>
        ) : (
          <button
            onClick={() => setGateOpen(true)}
            className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3.5 py-1.5 text-[13px] font-medium text-ink2 transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden className="text-ink3">
              <path d="M8 2 1.5 5 8 8l6.5-3L8 2Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
              <path d="M4.5 6.6V10c0 .9 1.6 1.6 3.5 1.6s3.5-.7 3.5-1.6V6.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Add your university
          </button>
        )}
      </div>

      <div className="grid gap-6 md:grid-cols-[270px_1fr]">
        {/* Context rail — the selected major's national estimates, or a way to
            pin one without leaving the chat. */}
        <aside className="min-w-0">
          {selected ? (
            <>
              <div className="mb-2 flex items-center justify-between gap-2">
                <span className="micro text-ink3">National estimates</span>
                {/* Back to the pick state to swap the pinned major. */}
                <a href="#/chat" className="micro text-accent hover:underline">
                  Change
                </a>
              </div>
              <MajorDetailCard major={selected} mode={mode} />
              <p className="mt-3 text-[12px] leading-relaxed text-ink3">
                These figures are national — the same for every school.
                {university
                  ? ` The advisor layers what ${university.name}’s program emphasizes on top, with citations.`
                  : ' Add your university to layer school-specific, cited guidance on top.'}
              </p>
            </>
          ) : (
            <div className="rounded-card border border-line bg-surface p-5">
              {intendedMatch ? (
                <>
                  <div className="micro text-ink3">Your intended major</div>
                  <button
                    onClick={() => pinMajor(intendedMatch)}
                    className="mt-2 flex w-full items-center justify-between gap-2 rounded-lg bg-ink px-3.5 py-2.5 text-left text-[13.5px] font-semibold text-page transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page"
                  >
                    <span className="truncate">Pin {intendedMatch.major}</span>
                    <span aria-hidden>→</span>
                  </button>
                  <div className="micro mt-3.5 text-ink3">Or pick another major</div>
                </>
              ) : (
                <>
                  <div className="micro text-ink3">Ground the advice</div>
                  <p className="mt-2 text-[13px] leading-relaxed text-ink2">
                    Pin a major to see its national estimates and ground every answer — or just
                    ask anything below.
                  </p>
                </>
              )}

              {/* Inline picker — pin a major without ever leaving the chat. */}
              <div className="mt-2">
                <SearchSpotlight
                  compact
                  majors={majors}
                  mode={mode}
                  query={pickQuery}
                  onQuery={setPickQuery}
                  onPick={pinMajor}
                />
              </div>

              <a
                href="#/explore"
                className="mt-3 inline-block text-[12.5px] font-medium text-ink3 transition-colors hover:text-ink"
              >
                Or explore the full map →
              </a>
            </div>
          )}
        </aside>

        {/* The advisor chat — a solid content surface (never glass). */}
        <section className="min-h-0">
          <div className="h-[min(72vh,760px)] overflow-hidden rounded-panel border border-line bg-surface">
            <AdvisorPanel key={selected?.cip ?? 'general'} major={selected} />
          </div>
        </section>
      </div>

      {/* Same gate the Explore panel raises, reachable here via "Add your university". */}
      <UniversityGateModal open={gateOpen} major={selected} onClose={() => setGateOpen(false)} />
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import UniversityPicker from './UniversityPicker'
import { useUniversity } from '../hooks/useUniversity'
import { useRoute } from '../hooks/useRoute'
import { EXPOSURE_STOPS } from '../design/tokens'
import type { University } from '../hooks/useUniversities'
import type { Major } from '../types'

// The school chip's violet — existing exposure-ramp stops, not a new token.
const VIOLET_INK = EXPOSURE_STOPS.light[4]

interface Props {
  open: boolean
  /** The major in play — seeds the intended-major field and pre-selects on /chat. */
  major: Major | null
  /** Called after any close (dismiss OR personalize) so the caller restores focus. */
  onClose: () => void
}

/** Soft upsell gate: a floating glass dialog (a legitimate glass surface) shown
 *  once, after the student's first advisor reply, when no school is set. The
 *  national advisor keeps working either way — "Maybe later" is remembered so it
 *  never nags again. */
export default function UniversityGateModal({ open, major, onClose }: Props) {
  const reduce = useReducedMotion()
  const { setUniversity, dismissGate } = useUniversity()
  const { nav } = useRoute()

  const [query, setQuery] = useState('')
  const [picked, setPicked] = useState<University | null>(null)
  const [intendedMajor, setIntendedMajor] = useState('')

  const dialogRef = useRef<HTMLDivElement>(null)
  const restoreRef = useRef<Element | null>(null)

  // Seed the intended major from the selected major each time the gate opens,
  // and remember what was focused so we can restore it on close.
  useEffect(() => {
    if (!open) return
    setIntendedMajor(major?.major ?? '')
    setPicked(null)
    setQuery('')
    restoreRef.current = document.activeElement
  }, [open, major])

  const close = () => {
    const el = restoreRef.current
    onClose()
    // Return focus to the advisor input (or whatever was focused before).
    if (el instanceof HTMLElement) requestAnimationFrame(() => el.focus())
  }
  const dismiss = () => {
    dismissGate()
    close()
  }
  const personalize = () => {
    if (!picked) return
    setUniversity({
      unitid: picked.unitid,
      name: picked.name,
      domain: picked.domain,
      intendedMajor: intendedMajor.trim() || picked.name,
    })
    close()
    nav('chat', major?.cip ?? undefined)
  }

  // Esc dismisses; Tab is trapped within the dialog.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        dismiss()
        return
      }
      if (e.key !== 'Tab' || !dialogRef.current) return
      const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])',
      )
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, picked, intendedMajor])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[60] grid place-items-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduce ? 0.12 : 0.2 }}
        >
          {/* Backdrop — click dismisses. */}
          <button
            aria-label="Dismiss"
            tabIndex={-1}
            onClick={dismiss}
            className="absolute inset-0 cursor-default bg-black/40"
          />
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="gate-title"
            initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.98, y: 8 }}
            transition={{ duration: reduce ? 0.12 : 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="glass relative w-full max-w-[440px] rounded-panel p-6 shadow-2xl shadow-black/25"
          >
            <div className="micro text-accent">Get full access</div>
            <h2 id="gate-title" className="mt-1.5 text-xl font-semibold tracking-tight text-ink">
              Add your university for advice built around your school
            </h2>
            <p className="mt-2 text-[13.5px] leading-relaxed text-ink2">
              Layer personalized, cited guidance from your program on top of the national
              exposure, pay, and growth data. The advisor keeps working without it — this just
              makes it yours.
            </p>

            <div className="mt-5 space-y-3">
              <label className="block">
                <span className="micro mb-1.5 block text-ink3">Your university</span>
                <UniversityPicker query={query} onQuery={setQuery} onPick={setPicked} autoFocus />
              </label>

              {picked && (
                <div className="micro flex items-center gap-1.5 text-ink2">
                  <span
                    aria-hidden
                    className="inline-block size-1.5 rounded-full"
                    style={{ background: VIOLET_INK }}
                  />
                  {picked.name} · {picked.domain}
                </div>
              )}

              <label className="block">
                <span className="micro mb-1.5 block text-ink3">Intended major</span>
                <input
                  value={intendedMajor}
                  onChange={(e) => setIntendedMajor(e.target.value)}
                  placeholder="e.g. Computer science"
                  aria-label="Intended major"
                  className="h-11 w-full rounded-xl border border-line bg-surface px-3.5 text-[15px] text-ink outline-none transition-shadow placeholder:text-ink3 focus:border-accent focus:shadow-md"
                />
              </label>
            </div>

            <div className="mt-6 flex items-center justify-end gap-2.5">
              <button
                type="button"
                onClick={dismiss}
                className="rounded-[10px] px-4 py-2.5 text-[13.5px] font-medium text-ink2 transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page"
              >
                Maybe later
              </button>
              <button
                type="button"
                onClick={personalize}
                disabled={!picked}
                className="rounded-[10px] bg-ink px-4 py-2.5 text-[13.5px] font-semibold text-page transition-opacity hover:opacity-90 disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page"
              >
                Personalize my advice →
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

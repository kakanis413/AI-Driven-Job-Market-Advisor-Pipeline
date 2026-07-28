import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { FOCUS_RING, FOCUS_RING_TIGHT } from '../design/classes'
import { exposureBand, exposureColor, fmtExposure, fmtPay, growthOf } from '../design/scales'
import { EASE, type Mode } from '../design/tokens'
import type { Major } from '../types'
import { CloseIcon } from './icons'

interface Props {
  major: Major
  mode: Mode
  open: boolean
  onClose: () => void
}

const slug = (s: string) =>
  s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'major'

/** A one-line, shareable summary — the number, its plain-language band, and the
 *  exposure-≠-job-loss framing, always kept together. */
function summaryOf(major: Major): string {
  const band = exposureBand(major.exposure)
  const scored = major.exposure !== null
  const bandNote = band.range ? ` (${band.label})` : ''
  return scored
    ? `${major.major} is ${fmtExposure(major.exposure)}/10 AI-exposed${bandNote} — the mix of tasks shifts, the field doesn’t vanish. via Major Visualizer`
    : `${major.major} isn’t scored for AI exposure yet. via Major Visualizer`
}

/** Personal, shareable result card. A floating glass dialog (legitimate glass
 *  surface) previews a token-styled 1080×1350 image rendered on an offscreen
 *  canvas, then offers native share (mobile) / download PNG / copy summary.
 *  No new dependency — pure canvas 2D. */
export default function ShareCard({ major, mode, open, onClose }: Props) {
  const reduce = useReducedMotion()
  const [pngUrl, setPngUrl] = useState<string | null>(null)
  const blobRef = useRef<Blob | null>(null)
  const [canShareFiles, setCanShareFiles] = useState(false)
  const [copied, setCopied] = useState(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  const restoreRef = useRef<Element | null>(null)

  const summary = summaryOf(major)

  // Render the card whenever the dialog opens (or the theme changes while open).
  useEffect(() => {
    if (!open) return
    restoreRef.current = document.activeElement
    let cancelled = false
    setPngUrl(null)
    drawShareCanvas(major, mode).then((blob) => {
      if (cancelled || !blob) return
      blobRef.current = blob
      setPngUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return URL.createObjectURL(blob)
      })
    })
    try {
      const probe = new File([new Blob()], 'x.png', { type: 'image/png' })
      setCanShareFiles(typeof navigator.canShare === 'function' && navigator.canShare({ files: [probe] }))
    } catch {
      setCanShareFiles(false)
    }
    return () => {
      cancelled = true
    }
  }, [open, major, mode])

  // Revoke the object URL on unmount.
  useEffect(
    () => () => {
      if (pngUrl) URL.revokeObjectURL(pngUrl)
    },
    [pngUrl],
  )

  const close = () => {
    onClose()
    const el = restoreRef.current
    if (el instanceof HTMLElement) requestAnimationFrame(() => el.focus())
  }

  // Esc closes; Tab is trapped within the dialog.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        close()
        return
      }
      if (e.key !== 'Tab' || !dialogRef.current) return
      const f = dialogRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input, [tabindex]:not([tabindex="-1"])',
      )
      if (f.length === 0) return
      const first = f[0]
      const last = f[f.length - 1]
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
  }, [open])

  const doShare = async () => {
    const blob = blobRef.current
    if (!blob) return
    const file = new File([blob], `${slug(major.major)}-ai-exposure.png`, { type: 'image/png' })
    try {
      await navigator.share({ files: [file], title: `${major.major} — AI exposure`, text: summary })
    } catch {
      /* user cancelled or the share sheet failed — no-op */
    }
  }
  const doDownload = () => {
    const blob = blobRef.current
    if (!blob) return
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${slug(major.major)}-ai-exposure.png`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }
  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(summary)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      /* clipboard blocked — the summary is still visible below to copy by hand */
    }
  }

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
          <button
            aria-label="Close"
            tabIndex={-1}
            onClick={close}
            className="absolute inset-0 cursor-default bg-black/40"
          />
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="share-title"
            initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.98, y: 8 }}
            transition={{ duration: reduce ? 0.12 : 0.22, ease: EASE }}
            className="glass relative w-full max-w-[380px] rounded-panel p-5 shadow-2xl shadow-black/25"
          >
            <div className="flex items-center justify-between gap-2">
              <h2 id="share-title" className="text-[15px] font-semibold text-ink">
                Share this major
              </h2>
              <button
                onClick={close}
                aria-label="Close"
                className={`grid size-7 place-items-center rounded-md text-ink3 transition-colors hover:bg-raised hover:text-ink ${FOCUS_RING_TIGHT}`}
              >
                <CloseIcon />
              </button>
            </div>

            {/* Preview of the generated image (scaled to the 1080×1350 ratio). */}
            <div className="mx-auto mt-4 w-[220px] overflow-hidden rounded-card border border-line">
              <div className="relative" style={{ aspectRatio: '1080 / 1350' }}>
                {pngUrl ? (
                  <img src={pngUrl} alt={summary} className="absolute inset-0 h-full w-full object-cover" />
                ) : (
                  <div className="absolute inset-0 grid place-items-center bg-raised">
                    <span className="micro text-ink3">Rendering…</span>
                  </div>
                )}
              </div>
            </div>

            <div className="mt-4 flex flex-col gap-2">
              {canShareFiles && (
                <button
                  onClick={doShare}
                  disabled={!pngUrl}
                  className={`h-10 rounded-[10px] bg-ink text-[13.5px] font-semibold text-page transition-opacity hover:opacity-90 disabled:opacity-40 ${FOCUS_RING}`}
                >
                  Share…
                </button>
              )}
              <div className="flex gap-2">
                <button
                  onClick={doDownload}
                  disabled={!pngUrl}
                  className={`h-10 flex-1 rounded-[10px] border border-line text-[13.5px] font-medium text-ink transition-colors hover:bg-raised disabled:opacity-40 ${FOCUS_RING} ${
                    canShareFiles ? '' : 'bg-surface'
                  }`}
                >
                  Download image
                </button>
                <button
                  onClick={doCopy}
                  className={`h-10 flex-1 rounded-[10px] border border-line text-[13.5px] font-medium text-ink transition-colors hover:bg-raised ${FOCUS_RING}`}
                >
                  {copied ? 'Copied ✓' : 'Copy summary'}
                </button>
              </div>
            </div>

            <p className="mt-3 text-[11.5px] leading-snug text-ink3">{summary}</p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/* -------------------------------------------------------------------------- */
/* Canvas rendering — token-styled, reads the live CSS custom properties so    */
/* light and dark both render correctly. Pure 2D API, no dependency.           */
/* -------------------------------------------------------------------------- */

async function drawShareCanvas(major: Major, mode: Mode): Promise<Blob | null> {
  const W = 1080
  const H = 1350
  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext('2d')
  if (!ctx) return null

  const cs = getComputedStyle(document.documentElement)
  const tok = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback
  const page = tok('--page', '#f4f3ef')
  const surface = tok('--surface', '#faf9f6')
  const ink = tok('--ink', '#191817')
  const ink2 = tok('--ink2', '#5a5852')
  const ink3 = tok('--ink3', '#6f6c63')
  const line = tok('--line', 'rgba(25,24,23,.1)')
  const accent = tok('--accent', '#2166bf')

  const sans = "'Instrument Sans Variable', system-ui, sans-serif"
  const serif = "'Playfair Display Variable', Georgia, serif"

  // Make sure the web fonts are ready so the canvas doesn't fall back.
  try {
    await (document as Document & { fonts?: FontFaceSet }).fonts?.ready
  } catch {
    /* fonts API unavailable — proceed with fallbacks */
  }

  // Page + inset card.
  ctx.fillStyle = page
  ctx.fillRect(0, 0, W, H)
  const pad = 64
  roundRect(ctx, pad, pad, W - 2 * pad, H - 2 * pad, 44)
  ctx.fillStyle = surface
  ctx.fill()
  ctx.lineWidth = 2
  ctx.strokeStyle = line
  ctx.stroke()

  const cx = W / 2
  const inner = pad + 72

  // Wordmark.
  ctx.textAlign = 'left'
  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = ink3
  ctx.font = `600 30px ${sans}`
  ctx.fillText('MAJOR VISUALIZER', inner, pad + 96)

  // Family.
  ctx.fillStyle = accent
  ctx.font = `600 30px ${sans}`
  ctx.fillText((major.family || '').toUpperCase(), inner, pad + 150)

  // Major name (display serif, wrapped, up to 2 lines).
  ctx.fillStyle = ink
  ctx.font = `640 72px ${serif}`
  const nameLines = wrap(ctx, major.major, W - 2 * inner).slice(0, 2)
  let ny = pad + 246
  for (const ln of nameLines) {
    ctx.fillText(ln, inner, ny)
    ny += 82
  }

  // Exposure ring — ramp-filled, matching the on-screen gauge: the fill sweeps
  // clockwise from the top through the ramp's own pale→deep colors up to the
  // score's position, flat track gray for the remainder. No separate band
  // label here — the ring's own color already carries that read, same as the
  // live card (see MajorDetailCard's Gauge for the identical approach).
  const scored = major.exposure !== null
  const score = major.exposure ?? 0
  const ringR = 210
  const ringCy = 760
  const ringW = 46
  // Track.
  ctx.beginPath()
  ctx.lineWidth = ringW
  ctx.strokeStyle = line
  ctx.arc(cx, ringCy, ringR, 0, Math.PI * 2)
  ctx.stroke()
  if (scored) {
    const N = 64
    const f = Math.max(0, Math.min(1, score / 10))
    const segCount = f > 0 ? Math.max(1, Math.round(N * f)) : 0
    const expC = exposureColor(mode)
    for (let i = 0; i < segCount; i++) {
      const t0 = i / N
      const t1 = Math.min((i + 1) / N + 0.004, f)
      const start = -Math.PI / 2 + t0 * Math.PI * 2
      const end = -Math.PI / 2 + t1 * Math.PI * 2
      ctx.beginPath()
      ctx.lineWidth = ringW
      ctx.lineCap = i === 0 || i === segCount - 1 ? 'round' : 'butt'
      ctx.strokeStyle = expC(t0 * 10)
      ctx.arc(cx, ringCy, ringR, start, end)
      ctx.stroke()
    }
    ctx.lineCap = 'butt'
  }
  // Score number.
  ctx.textAlign = 'center'
  ctx.fillStyle = ink
  ctx.font = `640 168px ${sans}`
  ctx.fillText(fmtExposure(major.exposure), cx, ringCy + 34)
  ctx.fillStyle = ink3
  ctx.font = `560 34px ${sans}`
  ctx.fillText(scored ? '/ 10 exposure' : 'not scored yet', cx, ringCy + 96)

  // Stats row: median pay + growth.
  const growth = growthOf(major.growth)
  const statY = 1150
  const statLabelY = statY - 4
  const colL = pad + 130
  const colR = W - pad - 130
  ctx.font = `560 26px ${sans}`
  ctx.fillStyle = ink3
  ctx.fillText('MEDIAN PAY', colL, statLabelY - 44)
  ctx.fillText('JOB GROWTH', colR, statLabelY - 44)
  ctx.font = `640 52px ${sans}`
  ctx.fillStyle = ink
  ctx.fillText(major.median_pay != null ? fmtPay(major.median_pay) : 'No data', colL, statY)
  ctx.fillText(major.growth ? growth.label : 'No data', colR, statY)

  // Caveat one-liner (wrapped).
  ctx.textAlign = 'center'
  ctx.font = `450 28px ${sans}`
  ctx.fillStyle = ink2
  const caveat = 'High exposure doesn’t mean the job disappears — the mix of tasks shifts.'
  const cLines = wrap(ctx, caveat, W - 2 * inner)
  let cy = H - pad - 96
  for (const ln of cLines) {
    ctx.fillText(ln, cx, cy)
    cy += 38
  }

  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), 'image/png'))
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function wrap(ctx: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  const words = text.split(/\s+/)
  const lines: string[] = []
  let cur = ''
  for (const w of words) {
    const trial = cur ? `${cur} ${w}` : w
    if (ctx.measureText(trial).width > maxW && cur) {
      lines.push(cur)
      cur = w
    } else {
      cur = trial
    }
  }
  if (cur) lines.push(cur)
  return lines
}

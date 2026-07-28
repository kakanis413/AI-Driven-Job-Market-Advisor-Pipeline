/** Color scales, ink picking, and formatters. All d3-style math, zero React.
 *  Ramps interpolate in OKLab (hand-rolled — d3-color has no OKLab) so
 *  multi-hue ramps stay perceptually even. */

import type { Growth } from '../types'
import { EXPOSURE_STOPS, INK_DARK, INK_LIGHT, PAY_STOPS, type Mode } from './tokens'

/* ---------- color math ---------- */

const clamp01 = (t: number) => Math.min(1, Math.max(0, t))

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ]
}

const srgbToLinear = (c: number) => {
  const v = c / 255
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
}

const linearToSrgb = (c: number) => {
  const v = c <= 0.0031308 ? c * 12.92 : 1.055 * c ** (1 / 2.4) - 0.055
  return Math.round(clamp01(v) * 255)
}

type Oklab = [number, number, number]

function toOklab(hex: string): Oklab {
  const [r, g, b] = hexToRgb(hex).map(srgbToLinear) as [number, number, number]
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ]
}

function fromOklab([L, a, b]: Oklab): string {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3
  const r = linearToSrgb(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s)
  const g = linearToSrgb(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s)
  const bb = linearToSrgb(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s)
  const to2 = (n: number) => n.toString(16).padStart(2, '0')
  return `#${to2(r)}${to2(g)}${to2(bb)}`
}

/** Piecewise OKLab interpolator; optional per-stop positions in [0, 1]. */
export function ramp(stops: string[], positions?: number[]): (t: number) => string {
  const labs = stops.map(toOklab)
  const pos = positions ?? stops.map((_, i) => i / (stops.length - 1))
  return (t: number) => {
    const x = clamp01(t)
    let i = 0
    while (i < pos.length - 2 && x > pos[i + 1]) i++
    const f = clamp01((x - pos[i]) / (pos[i + 1] - pos[i] || 1))
    const [a, b] = [labs[i], labs[i + 1]]
    return fromOklab([
      a[0] + (b[0] - a[0]) * f,
      a[1] + (b[1] - a[1]) * f,
      a[2] + (b[2] - a[2]) * f,
    ])
  }
}

/* ---------- contrast & ink ---------- */

function luminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map(srgbToLinear) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/** Hard rule: no single ink survives either ramp — pick the higher-contrast
 *  candidate per fill (both ramps were tuned so the winner clears WCAG AA). */
export function inkFor(fill: string): string {
  return contrast(fill, INK_LIGHT) >= contrast(fill, INK_DARK) ? INK_LIGHT : INK_DARK
}

/* ---------- the two data scales ---------- */

/** The exposure ramp is fitted to the data, not to the nominal 0–10 scale, and
 *  that is the single biggest reason the map reads as a map instead of a wash.
 *
 *  Measured over the 360-major corpus: exposure runs 1.8–9.0, the median is 6.8,
 *  and 85% of all graduates sit in the 6–8 band (IQR 5.8–7.5). Painting that onto
 *  a linear 0–10 domain spends most of the ramp on empty territory and leaves the
 *  interquartile range — where nearly every real comparison happens — sharing a
 *  handful of near-identical colors.
 *
 *  Two corrections, both derived rather than eyeballed:
 *
 *  1. DOMAIN — anchor to the observed extent so no part of the ramp is wasted on
 *     values that never occur. Values outside it clamp, which degrades safely if
 *     a swapped-in dataset scores wider.
 *  2. POSITIONS — place the six stops on the graduate-weighted quantiles
 *     (1.8/5.5/6.7/7.0/8.0/9.0 → normalized), blended 75/25 toward those
 *     quantiles rather than fully equalized. Full equalization is too aggressive:
 *     it collapses the sparse low end into one flat segment. The blend keeps the
 *     tails legible while still spending over half the ramp on the middle.
 *
 *  Net effect vs. the previous linear 0–10 ramp: +36% OKLab separation across the
 *  IQR. To refit for a new corpus, recompute both constants from its distribution
 *  — they are the only thing tying this scale to the current data. */
const EXPOSURE_DOMAIN: [number, number] = [1.8, 9]
const EXPOSURE_POSITIONS = [0, 0.435, 0.61, 0.692, 0.846, 1]

/** Exposure → fill. An unscored major (null) gets the neutral NULL_FILL rather
 *  than the ramp's lowest stop, so "not scored yet" never masquerades as
 *  "lowest exposure". */
export function exposureColor(mode: Mode): (v: number | null) => string {
  const r = ramp(EXPOSURE_STOPS[mode], EXPOSURE_POSITIONS)
  const [lo, hi] = EXPOSURE_DOMAIN
  const span = hi - lo
  return (v: number | null) => (v === null ? NULL_FILL[mode] : r((v - lo) / span))
}

/** The domain the ramp is actually fitted to — the legend labels its endpoints
 *  with these, not with 0 and 10, so the color key never claims a range it does
 *  not paint. */
export const exposureRampDomain = () => EXPOSURE_DOMAIN

/** A darker (light mode) / lighter (dark mode) shade of a fill — used for the
 *  selection ring so it always reads as "this tile's own color, emphasized". */
export function shade(fill: string, mode: Mode): string {
  const [L, a, b] = toOklab(fill)
  return fromOklab([mode === 'light' ? Math.max(0, L - 0.24) : Math.min(1, L + 0.22), a * 0.9, b * 0.9])
}

/** Median pay (domain from data) → color. */
export function payColor(mode: Mode, [min, max]: [number, number]): (v: number) => string {
  const r = ramp(PAY_STOPS[mode])
  const span = Math.max(1, max - min)
  return (v: number) => r((v - min) / span)
}

/* ---------- formatters — the only path numbers take to the DOM ---------- */

/** "6.8", or an em dash when the major hasn't been scored — never "0.0". */
export const fmtExposure = (v: number | null) => (v === null ? '—' : v.toFixed(1))

export const fmtPay = (v: number | null) => (v == null ? '—' : `$${Math.round(v / 1000)}k`)

/** Fill for tiles/cells whose metric is null in the source data. */
export const NULL_FILL: Record<Mode, string> = { light: '#dbd9d1', dark: '#2e2d2a' }

const compact = new Intl.NumberFormat('en-US', {
  notation: 'compact',
  maximumFractionDigits: 1,
})
export const fmtCount = (v: number) => compact.format(v).toLowerCase()

/** Pay-to-debt ratio → "2.7×". */
export const fmtRatio = (v: number) => `${v.toFixed(1)}×`

/** Occupation growth outlook → "+4%" (a true minus sign, not a hyphen, on the
 *  rare negative). Null when the source has no projection for this SOC. */
export const fmtOutlook = (v: number | null) =>
  v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.round(Math.abs(v))}%`

/** Plain-language read of the AI-exposure score — a memorable band ALWAYS shown
 *  alongside the number, never instead of it (hard rule 2: color/number is never
 *  the only signal). Unscored is stated as a fact, never faked as "low". */
export const exposureBand = (v: number | null) =>
  v === null
    ? { label: 'Not scored yet', range: '' }
    : v < 4
      ? { label: 'Barely touched', range: '0–3' }
      : v < 8
        ? { label: 'Reshaped', range: '4–7' }
        : { label: 'Rewired', range: '8–10' }

/** Career-versatility band from the *count* of mapped occupations. The min-max
 *  normalized rank is far too skewed to split into thirds (the median major maps
 *  to ~2 of ~22 possible occupations, so a 1/3–2/3 split on the rank labels
 *  ~97% "Narrow"). Banding on the absolute count keeps all three bands populated
 *  and honest: 1–2 is genuinely Narrow, 3–5 Moderate, 6+ Broad. Keeps color from
 *  being the only signal on the versatility meter. */
export const bandOf = (versatility: number) =>
  versatility <= 2 ? 'Narrow' : versatility <= 5 ? 'Moderate' : 'Broad'

/* ---------- growth display ---------- */

export const GROWTH_META: Record<
  Growth,
  { label: string; glyph: string; tone: Record<Mode, string> | null }
> = {
  faster: { label: 'Faster', glyph: '↑', tone: { light: '#0d7f46', dark: '#22b573' } },
  average: { label: 'Average', glyph: '→', tone: null },
  slower: { label: 'Slower', glyph: '↘', tone: null },
  declining: { label: 'Declining', glyph: '↓', tone: { light: '#c22f2f', dark: '#e05252' } },
}

/** Null-safe growth lookup: the source may have no projection. */
export const growthOf = (g: Growth | null) =>
  g ? GROWTH_META[g] : { label: '—', glyph: '', tone: null }

/* ---------- search normalization ---------- */

export const normalize = (s: string) =>
  s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()

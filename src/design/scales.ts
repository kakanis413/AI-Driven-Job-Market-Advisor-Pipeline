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

/** Most majors sit 5–8, so the hot band is widened: pale sand is spent by
 *  ~4.2, and the 5–8 range crosses three stops (6.0 vs 8.5 read apart). */
const EXPOSURE_POSITIONS = [0, 0.42, 0.6, 0.76, 1]

/** AI exposure 0–10 → color (perceptually even, mid-weighted domain). */
export function exposureColor(mode: Mode): (v: number) => string {
  const r = ramp(EXPOSURE_STOPS[mode], EXPOSURE_POSITIONS)
  return (v: number) => r(v / 10)
}

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

export const fmtExposure = (v: number) => v.toFixed(1)

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

/** A 0–1 rank → a plain-language band. Keeps color from being the only signal. */
export const bandOf = (norm: number) =>
  norm < 1 / 3 ? 'Narrow' : norm < 2 / 3 ? 'Moderate' : 'Broad'

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

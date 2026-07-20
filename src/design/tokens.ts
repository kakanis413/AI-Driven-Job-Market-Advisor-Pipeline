/** Design tokens — the only source of raw values. See CLAUDE.md § Design system.
 *  Chrome colors (surfaces/ink) live as CSS custom properties in index.css;
 *  this module owns the data ramps and motion constants. */

import type { Family } from '../types'

export type Mode = 'light' | 'dark'
export type Layer = 'exposure' | 'pay'

/** Exposure ramp stops, "violet depth": pale lilac (low) → deep violet (high).
 *  Violet is deliberate. Exposure is a MAGNITUDE, not a verdict: red reads as
 *  danger and would contradict our own pinned caveat (high exposure does NOT
 *  mean the job disappears), while green would read as "safe". Violet carries
 *  neither valence — it reads as intensity — and stays clearly distinct from the
 *  sequential-blue pay ramp, so flipping the layer toggle is unmistakable.
 *  Luminance is monotonic, so it survives CVD without relying on hue.
 *  Interpolated in OKLab. Dark mode is its own selected set, never an auto-flip.
 *  Every stop is contrast-verified against `inkFor` (≥4.5:1 at all stops). */
export const EXPOSURE_STOPS: Record<Mode, string[]> = {
  light: ['#efe9f3', '#d5c8e4', '#b09ccc', '#8567ab', '#432c63'],
  dark: ['#2b2338', '#463862', '#69538f', '#9078bb', '#c3b2dd'],
}

/** Sequential blue for median pay. Dark mode flips the anchor so "near zero"
 *  recedes into the dark surface. */
export const PAY_STOPS: Record<Mode, string[]> = {
  light: ['#cde2fb', '#9ec5f4', '#5598e7', '#2a78d6', '#1c5cab', '#0d366b'],
  dark: ['#123055', '#1c5cab', '#2a78d6', '#5598e7', '#9ec5f4', '#cde2fb'],
}

/** The two candidate inks for text printed on ramp fills. */
export const INK_LIGHT = '#ffffff'
export const INK_DARK = '#191817'

/** Glass — floating surfaces ONLY (header, sticky toolbar, chat panel, tooltip,
 *  detail card). Never on tiles/cells or anything encoding data: translucency
 *  corrupts the color encoding. Mirrored as --glass-* CSS vars in index.css;
 *  the `.glass` utility there carries the blur + an @supports opaque fallback. */
export const GLASS = {
  light: {
    bg: 'rgba(250, 249, 246, 0.72)',
    border: 'rgba(25, 24, 23, 0.08)',
    blur: '16px',
  },
  dark: {
    bg: 'rgba(20, 19, 18, 0.68)',
    border: 'rgba(244, 243, 239, 0.10)',
    blur: '16px',
  },
} as const

/** The one spatial spring — every layout move in the app uses this so motion
 *  feels like a single system. */
export const SPRING = { type: 'spring', stiffness: 260, damping: 32 } as const

/** Reduced-motion replacement for the spring: a quick fade-length tween. */
export const REDUCED_TWEEN = { duration: 0.15 } as const

export const EASE = [0.22, 1, 0.36, 1] as const

/** Fixed family order: clusters the treemap and orders filter chips. */
export const FAMILY_ORDER: Family[] = [
  'STEM',
  'Business',
  'Health',
  'Social sci',
  'Humanities',
  'Arts',
  'Trades',
  'Other',
]

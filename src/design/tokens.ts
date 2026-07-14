/** Design tokens — the only source of raw values. See CLAUDE.md § Design system.
 *  Chrome colors (surfaces/ink) live as CSS custom properties in index.css;
 *  this module owns the data ramps and motion constants. */

import type { Family } from '../types'

export type Mode = 'light' | 'dark'
export type Layer = 'exposure' | 'pay'

/** Exposure ramp stops, "ember": pale sand (low) → gold → copper → oxblood
 *  (high). Single warm heat ramp — no green, so low exposure reads as "cool",
 *  not "safe" (see the pinned caveat). Luminance is monotonic, which the old
 *  green→red ramp was not, so it survives CVD without relying on hue.
 *  Interpolated in OKLab. Dark mode is its own selected set, never an
 *  auto-flip. Every stop is contrast-verified against `inkFor` (see CLAUDE.md). */
export const EXPOSURE_STOPS: Record<Mode, string[]> = {
  light: ['#ecd79f', '#dcae5e', '#c97c3d', '#ad4c2e', '#7f2d2a'],
  dark: ['#564834', '#8a6a38', '#bb7f42', '#d9764b', '#ee5b4c'],
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

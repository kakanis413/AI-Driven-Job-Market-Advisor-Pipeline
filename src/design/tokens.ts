/** Design tokens — the only source of raw values. See CLAUDE.md § Design system.
 *  Chrome colors (surfaces/ink) live as CSS custom properties in index.css;
 *  this module owns the data ramps and motion constants. */

import type { Family } from '../types'

export type Mode = 'light' | 'dark'
export type Layer = 'exposure' | 'pay'

/** Exposure ramp stops, "pastel greenery": pale mint (low) → deep teal (high).
 *  Exposure is a MAGNITUDE, not a verdict, so read this ramp as intensity, not
 *  as "safe → danger" — the pinned caveat (high exposure does NOT mean the job
 *  disappears) still governs. Luminance is monotonic low→high, so it survives
 *  CVD without relying on hue, and it stays clearly distinct from the
 *  sequential-blue pay ramp so flipping the layer toggle is unmistakable.
 *  Interpolated in OKLab. Dark mode is its own selected set, never an auto-flip.
 *
 *  SIX stops, not five, and the ends run paler/deeper than the hand-picked
 *  midtones: the ramp is anchored to the observed exposure range and positioned
 *  on the graduate-weighted quantiles (`EXPOSURE_DOMAIN` / `EXPOSURE_POSITIONS`
 *  in scales.ts), so the extra stop and the wider span buy resolution exactly
 *  where the majors pile up. Measured against the previous 5-stop 0–10 version,
 *  this separates the interquartile range (5.8→7.5) by 36% more OKLab distance.
 *  Verified ≥4.59:1 against `inkFor` at every point along both ramps — not just
 *  at the stops (see the INK_DARK note for why that floor is what it is). */
export const EXPOSURE_STOPS: Record<Mode, string[]> = {
  light: ['#d0f0e8', '#66c1b7', '#2ea69a', '#04877a', '#036659', '#003d31'],
  dark: ['#003d31', '#036659', '#04877a', '#2ea69a', '#66c1b7', '#d0f0e8'],
}

/** Sequential blue for median pay. Dark mode flips the anchor so "near zero"
 *  recedes into the dark surface. */
export const PAY_STOPS: Record<Mode, string[]> = {
  light: ['#cde2fb', '#9ec5f4', '#5598e7', '#2a78d6', '#1c5cab', '#0d366b'],
  dark: ['#123055', '#1c5cab', '#2a78d6', '#5598e7', '#9ec5f4', '#cde2fb'],
}

/** The two candidate inks for text printed on ramp fills.
 *
 *  INK_DARK is pure black here, not the `#191817` used for page ink, and that
 *  is forced by arithmetic. Any ramp that runs light→dark passes through the
 *  luminance where white and dark ink tie, and the contrast AT that crossover is
 *  the best either ink can do. Solving (Y+.05)² = 1.05·(Y_ink+.05) gives a
 *  ceiling of 4.21:1 with `#191817` — so the old ramp dipped to 4.22:1 and quietly
 *  missed AA in a narrow band, whatever the stops measured. Pure black lifts that
 *  floor to 4.58:1, which clears it. On a saturated tile fill the two are
 *  indistinguishable; this only ever prints on ramp colors, never on a surface. */
export const INK_LIGHT = '#ffffff'
export const INK_DARK = '#000000'

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

/** Row rhythm shared by the Table (grid) and the ROI board, so the two list
 *  views keep the same height and hairline cadence and switching between them
 *  never shifts the reading line. */
export const TABLE_ROW_H = 44
export const TABLE_HEAD_H = 34

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

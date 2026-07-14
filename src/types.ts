/** The data contract — see CLAUDE.md. `public/data.json` and any URL passed
 *  via VITE_DATA_URL must conform to `Major[]`. */

export type Family =
  | 'STEM'
  | 'Business'
  | 'Health'
  | 'Social sci'
  | 'Humanities'
  | 'Arts'
  | 'Trades'
  | 'Other'

export type Growth = 'declining' | 'slower' | 'average' | 'faster'

export interface Occupation {
  soc: string
  title: string
  /** AI exposure 0–10 for this occupation */
  exposure: number
}

export interface Major {
  /** CIP code, e.g. "11.0701" */
  cip: string
  major: string
  family: Family
  /** annual degree completions — drives tile area */
  completions: number
  /** AI exposure 0–10 */
  exposure: number
  /** median pay, USD — null when the source has no estimate */
  median_pay: number | null
  /** null when the source has no projection */
  growth: Growth | null
  occupations: Occupation[]
  rationale: string
}

/** Shared tooltip payload (client coords + the hovered major). */
export interface TipData {
  major: Major
  x: number
  y: number
}

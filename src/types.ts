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
  /** AI exposure 0–10 for this occupation, or null when unscored. */
  exposure: number | null
}

export interface Major {
  /** CIP code, e.g. "11.0701" */
  cip: string
  major: string
  family: Family
  /** annual degree completions — drives tile area */
  completions: number
  /** AI exposure 0–10, or null when the pipeline hasn't scored it yet. */
  exposure: number | null
  /** median pay, USD — null when the source has no estimate */
  median_pay: number | null
  /** null when the source has no projection */
  growth: Growth | null
  occupations: Occupation[]
  rationale: string
  /** Early-career pay ÷ typical student debt (e.g. 2.7 → earns 2.7× the debt).
   *  Optional: absent in the bundled sample; supplied by the pipeline. */
  payToDebt?: number | null
  /** payToDebt's 0–1 rank across all majors — drives the meter fill. */
  payToDebtRank?: number | null
  /** Count of distinct occupations the major maps to (higher = more flexible). */
  versatility?: number | null
  /** versatility's 0–1 rank across all majors — drives the meter fill. */
  versatilityRank?: number | null
}

/** Shared tooltip payload (client coords + the hovered major). */
export interface TipData {
  major: Major
  x: number
  y: number
}

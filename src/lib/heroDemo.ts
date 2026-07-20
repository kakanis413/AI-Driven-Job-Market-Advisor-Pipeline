/** Demo exposure for the LANDING hero only.
 *
 *  The real pipeline hasn't scored exposure yet — every major currently reads
 *  5.0, so the violet ramp renders one flat lavender no matter how saturated the
 *  hero is (see UI_REDESIGN.md § "The blocker on colorful"). To let the ramp
 *  show its range on the illustrative landing, we synthesize a varied exposure
 *  per major: a realistic per-family base plus a deterministic per-major jitter.
 *
 *  Applied to the REAL majors (real names + CIPs), so hovering shows a real name
 *  and clicking still resolves to that major in Explore. The `SAMPLE DATA` badge
 *  keeps this honest. Explore itself always uses the real (5.0) data. */

import type { Family, Major } from '../types'

/** Rough, defensible per-family centers: how AI-reachable the field's typical
 *  task mix is. Not scores — illustration until the pipeline lands. */
const FAMILY_BASE: Record<Family, number> = {
  STEM: 7.6,
  Business: 6.7,
  Health: 4.7,
  'Social sci': 5.5,
  Humanities: 6.1,
  Arts: 4.0,
  Trades: 3.1,
  Other: 5.2,
}

/** Stable FNV-1a hash of the CIP → deterministic jitter so a major keeps the
 *  same demo color across renders (no flicker) while tiles within a family vary. */
export function demoExposure(m: Major): number {
  const base = FAMILY_BASE[m.family] ?? 5
  let h = 2166136261
  for (let i = 0; i < m.cip.length; i++) {
    h ^= m.cip.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  const jitter = (((h >>> 0) % 1000) / 1000 - 0.5) * 3.2 // ±1.6
  return Math.max(0.6, Math.min(9.7, base + jitter))
}

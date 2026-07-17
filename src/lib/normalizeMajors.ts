/** Adapter from the pipeline's raw `data.json` rows to the app's `Major`
 *  contract (see CLAUDE.md § Data contract). The pipeline emits a wider,
 *  differently-named schema (`graduates`, numeric CIP-series `family`, a 0–1
 *  `exposure`, no `cip`/`rationale`); the UI is written against the normalized
 *  `Major` shape. Keeping the translation here means components never learn the
 *  raw field names — the data layer stays a contract, not a hardcode. */

import type { Family, Growth, Major, Occupation } from '../types'

/** A row as produced by the Python pipeline. Every field is optional/loose
 *  because upstream stages fill them in incrementally (e.g. `ai_exposure_norm`
 *  is null until AI scoring runs). */
interface RawMajor {
  major?: unknown
  major_name?: unknown
  /** 2-digit CIP series, e.g. "52" — NOT a display family. */
  family?: unknown
  graduates?: unknown
  completions?: unknown
  cip?: unknown
  pay_to_debt_ratio?: unknown
  pay_to_debt_ratio_norm?: unknown
  versatility?: unknown
  versatility_norm?: unknown
  exposure?: unknown
  ai_exposure?: unknown
  ai_exposure_norm?: unknown
  median_pay?: unknown
  growth?: unknown
  occupations?: unknown
  rationale?: unknown
}

/** 2-digit CIP series → display family group. The series is the real signal in
 *  the pipeline data; this collapses ~40 series into the 7 + Other buckets the
 *  treemap clusters by. Anything unlisted falls through to 'Other'. */
const CIP_FAMILY: Record<string, Family> = {
  '01': 'STEM', // Agriculture
  '03': 'STEM', // Natural resources & conservation
  '04': 'STEM', // Architecture
  '11': 'STEM', // Computer & information sciences
  '14': 'STEM', // Engineering
  '15': 'STEM', // Engineering technologies
  '26': 'STEM', // Biological & biomedical sciences
  '27': 'STEM', // Mathematics & statistics
  '40': 'STEM', // Physical sciences
  '41': 'STEM', // Science technologies
  '52': 'Business', // Business, management, marketing
  '51': 'Health', // Health professions
  '31': 'Health', // Parks, recreation, leisure & fitness
  '05': 'Social sci', // Area, ethnic, cultural, gender studies
  '13': 'Social sci', // Education
  '19': 'Social sci', // Family & consumer / human sciences
  '22': 'Social sci', // Legal professions & studies
  '42': 'Social sci', // Psychology
  '43': 'Social sci', // Homeland security, law enforcement
  '44': 'Social sci', // Public administration & social service
  '45': 'Social sci', // Social sciences
  '09': 'Humanities', // Communication & journalism
  '16': 'Humanities', // Foreign languages & linguistics
  '23': 'Humanities', // English language & literature
  '24': 'Humanities', // Liberal arts & sciences, general studies
  '38': 'Humanities', // Philosophy & religious studies
  '39': 'Humanities', // Theology & religious vocations
  '54': 'Humanities', // History
  '50': 'Arts', // Visual & performing arts
  '10': 'Trades', // Communications technologies
  '12': 'Trades', // Culinary & personal services
  '46': 'Trades', // Construction trades
  '47': 'Trades', // Mechanic & repair technologies
  '48': 'Trades', // Precision production
  '49': 'Trades', // Transportation & materials moving
  '25': 'Other', // Library science
  '29': 'Other', // Military technologies
  '30': 'Other', // Multi / interdisciplinary studies
}

const GROWTH_VALUES: readonly Growth[] = ['declining', 'slower', 'average', 'faster']

const str = (v: unknown): string | null => (typeof v === 'string' && v.length > 0 ? v : null)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** The raw `exposure`/`ai_exposure_norm` fields are on a 0–1 scale; the UI works
 *  in 0–10. Values already >1 are assumed to be pre-scaled. Null-safe. */
function toExposure(raw: RawMajor): number {
  const v = num(raw.ai_exposure_norm) ?? num(raw.ai_exposure) ?? num(raw.exposure) ?? 0
  const scaled = v <= 1 ? v * 10 : v
  return Math.max(0, Math.min(10, scaled))
}

function toOccupations(v: unknown): Occupation[] {
  if (!Array.isArray(v)) return []
  return v
    .map((o): Occupation | null => {
      if (typeof o !== 'object' || o === null) return null
      const r = o as Record<string, unknown>
      const soc = str(r.soc)
      const title = str(r.title)
      if (!soc || !title) return null
      return { soc, title, exposure: toExposure(r as RawMajor) }
    })
    .filter((o): o is Occupation => o !== null)
}

function toMajor(raw: RawMajor, index: number): Major | null {
  const major = str(raw.major) ?? str(raw.major_name)
  if (!major) return null

  const series = str(raw.family) ?? ''
  const family: Family = CIP_FAMILY[series] ?? 'Other'
  // The pipeline dropped the detailed CIP code, keeping only the 2-digit
  // series. Synthesize a stable, unique id from series + ordinal so it can key
  // React lists and drive selection; it reads like a CIP for the detail card.
  const cip = str(raw.cip) ?? `${series || '00'}.${String(index).padStart(4, '0')}`

  const growthRaw = str(raw.growth)
  const growth: Growth | null =
    growthRaw && (GROWTH_VALUES as readonly string[]).includes(growthRaw)
      ? (growthRaw as Growth)
      : null

  return {
    cip,
    major,
    family,
    completions: num(raw.completions) ?? num(raw.graduates) ?? 0,
    exposure: toExposure(raw),
    median_pay: num(raw.median_pay),
    growth,
    occupations: toOccupations(raw.occupations),
    rationale:
      str(raw.rationale) ??
      'AI-exposure scoring for this major is still pending in the data pipeline.',
    payToDebt: num(raw.pay_to_debt_ratio),
    payToDebtRank: num(raw.pay_to_debt_ratio_norm),
    versatility: num(raw.versatility),
    versatilityRank: num(raw.versatility_norm),
  }
}

/** Parse+normalize a raw `data.json` payload into `Major[]`. Invalid rows (no
 *  name) are dropped; the caller reports the count. Throws on a non-array. */
export function normalizeMajors(json: unknown): Major[] {
  if (!Array.isArray(json)) throw new Error('expected a JSON array of majors')
  const out: Major[] = []
  for (let i = 0; i < json.length; i++) {
    const m = toMajor(json[i] as RawMajor, i)
    if (m) out.push(m)
  }
  return out
}

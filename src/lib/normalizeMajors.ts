/** Adapter from the pipeline's raw `data.json` rows to the app's `Major`
 *  contract (see CLAUDE.md § Data contract). The pipeline emits a wider,
 *  differently-named schema (`graduates`, numeric CIP-series `family`, a 0–1
 *  `exposure`, no `cip`/`rationale`); the UI is written against the normalized
 *  `Major` shape. Keeping the translation here means components never learn the
 *  raw field names — the data layer stays a contract, not a hardcode. */

import type { Family, Growth, Major, Occupation, TopCareer } from '../types'

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
  top_careers?: unknown
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
  // Communications technologies — Graphic Communications and Audiovisual
  // Technologies are design/media production, not a trade. Filing them under
  // Trades put 4,657 of that family's 11,255 graduates in the wrong bucket and
  // made "Trades" look like it was mostly graphic designers.
  '10': 'Arts',
  '12': 'Trades', // Culinary & personal services
  '46': 'Trades', // Construction trades
  '47': 'Trades', // Mechanic & repair technologies
  '48': 'Trades', // Precision production
  '49': 'Trades', // Transportation & materials moving
  '25': 'Humanities', // Library science
  '29': 'Other', // Military technologies
  '30': 'Other', // Multi / interdisciplinary studies — see CIP30_FAMILY
}

/** CIP 30 ("Multi/Interdisciplinary Studies") is a 42-major grab bag, and
 *  bucketing it wholesale into 'Other' built a junk drawer: Cognitive Science,
 *  Nutrition Sciences, Data Science and International Studies are real majors
 *  with obvious homes, and burying them cost 'Other' its meaning. The series is
 *  the only case where the 2-digit code genuinely cannot decide the family, so
 *  it gets an explicit per-major table — matched on the exact `major` string.
 *
 *  Anything not listed stays 'Other', which is now honest: it holds the two
 *  genuinely unclassifiable "Multi-/Interdisciplinary Studies, General/Other"
 *  rows plus the military series. */
const CIP30_FAMILY: Record<string, Family> = {
  'Nutrition Sciences': 'STEM',
  'Biological and Physical Sciences': 'STEM',
  'Cognitive Science': 'STEM',
  'Human Biology': 'STEM',
  'Mathematics and Computer Science': 'STEM',
  'Natural Sciences': 'STEM',
  'Human Computer Interaction': 'STEM',
  'Systems Science and Theory': 'STEM',
  'Data Analytics': 'STEM',
  'Computational Science': 'STEM',
  Biopsychology: 'STEM',
  'Marine Sciences': 'STEM',
  'Data Science': 'STEM',
  'Earth Systems Science': 'STEM',
  'Environmental Geosciences': 'STEM',
  Anthrozoology: 'STEM',
  'Accounting and Computer Science': 'STEM',
  'Economics and Computer Science': 'STEM',
  'International/Globalization Studies': 'Social sci',
  'Behavioral Sciences': 'Social sci',
  'Sustainability Studies': 'Social sci',
  'Science, Technology and Society': 'Social sci',
  'Peace Studies and Conflict Resolution': 'Social sci',
  Gerontology: 'Social sci',
  'Intercultural/Multicultural and Diversity Studies': 'Social sci',
  'Philosophy, Politics, and Economics': 'Social sci',
  'History and Political Science': 'Social sci',
  'Geography and Environmental Studies': 'Social sci',
  'Mathematical Economics': 'Social sci',
  'Dispute Resolution': 'Social sci',
  'Classical and Ancient Studies': 'Humanities',
  'Cultural Studies/Critical Theory and Analysis': 'Humanities',
  'Historic Preservation and Conservation': 'Humanities',
  'Museology/Museum Studies': 'Humanities',
  'Medieval and Renaissance Studies': 'Humanities',
  'Maritime Studies': 'Humanities',
  'Holocaust and Related Studies': 'Humanities',
  'Cultural Studies and Comparative Literature': 'Humanities',
  'Digital Humanities and Textual Studies': 'Humanities',
  'History and Language/Literature': 'Humanities',
}

const GROWTH_VALUES: readonly Growth[] = ['declining', 'slower', 'average', 'faster']

const str = (v: unknown): string | null => (typeof v === 'string' && v.length > 0 ? v : null)
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** The raw `exposure`/`ai_exposure_norm` fields are on a 0–1 scale; the UI works
 *  in 0–10. Values already >1 are assumed to be pre-scaled. Null-safe. */
function toExposure(raw: RawMajor): number | null {
  // null, not 0 — an unscored major is "not scored yet", and rendering it as 0
  // would read as the LOWEST exposure, which is a different (false) claim.
  const v = num(raw.ai_exposure_norm) ?? num(raw.ai_exposure) ?? num(raw.exposure)
  if (v === null) return null
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

/** `top_careers` rows use the pipeline's own field names (`soc_code`,
 *  `occupation_title`, `median_wage_annual`, `outlook_pct`) — translated here
 *  same as `toOccupations`, so the component never learns the raw shape.
 *  Sorted by rank in case the source ever ships out of order. */
function toTopCareers(v: unknown): TopCareer[] {
  if (!Array.isArray(v)) return []
  return v
    .map((c): TopCareer | null => {
      if (typeof c !== 'object' || c === null) return null
      const r = c as Record<string, unknown>
      const soc = str(r.soc_code)
      const title = str(r.occupation_title)
      const rank = num(r.rank)
      if (!soc || !title || rank === null) return null
      return {
        rank,
        soc,
        title,
        medianWage: num(r.median_wage_annual),
        outlookPct: num(r.outlook_pct),
      }
    })
    .filter((c): c is TopCareer => c !== null)
    .sort((a, b) => a.rank - b.rank)
}

function toMajor(raw: RawMajor, index: number): Major | null {
  const major = str(raw.major) ?? str(raw.major_name)
  if (!major) return null

  const series = str(raw.family) ?? ''
  const family: Family =
    (series === '30' ? CIP30_FAMILY[major] : undefined) ?? CIP_FAMILY[series] ?? 'Other'
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
    topCareers: toTopCareers(raw.top_careers),
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

# Claude Code prompt — UX / Gen-Z / cleanliness polish

A frontend-only pass to make Major Visualizer more personal, shareable, and clean. Stay entirely within `CLAUDE.md`: paper & ink tokens, the violet exposure ramp, glass only on floating surfaces, WCAG AA (tile ink via `inkFor`), visible focus rings, full keyboard path, `prefers-reduced-motion` → ≤150ms opacity fades, every number through the `scales.ts` formatters, the pinned footer caveat untouched. No raw hex, no default Tailwind palette. Grounded in the real files noted per task.

## A. Plain-language exposure bands (`src/design/scales.ts`)

Add a helper next to `bandOf`:
```ts
export const exposureBand = (v: number | null) =>
  v === null ? { label: 'Not scored yet', range: '' }
  : v < 4  ? { label: 'Barely touched', range: '0–3' }
  : v < 8  ? { label: 'Reshaped',       range: '4–7' }
  :          { label: 'Rewired',        range: '8–10' }
```
Bands are a memorable, plain-language read of the score — always shown WITH the numeric score, never replacing it (hard rule 2: color/number is never the only signal).

## B. Personal, shareable result card (`src/components/MajorDetailCard.tsx` + new `src/components/ShareCard.tsx`)

`MajorDetailCard` is already the detail surface (used in the Explore advisor panel and the `/chat` rail). Make it read as "your major," and make it shareable.

1. Under the `Gauge`, add a one-line band + verdict: the `exposureBand(major.exposure).label` as a small pill (violet ramp stop `#efe9f3` fill / `#432c63` ink — existing stops, no new token), followed by the existing caveat framing in plain words, e.g. "High exposure — a lot of the day-to-day is AI-reachable, so the skill mix shifts, the field doesn't vanish." Keep it to one sentence; scale the wording by band.
2. Add a quiet "Share" action in the card header (icon + label). On click it opens/ög generates a shareable card via a new `ShareCard` component:
   - `ShareCard` renders the major's name, the big exposure score inside the violet ring, the band label, median pay, and growth onto an offscreen `<canvas>` sized for social (e.g. 1080×1350), styled from the design tokens (read the CSS custom properties off `:root` so light/dark both work). No new dependency — draw with the canvas 2D API.
   - Offer three outcomes, in order of availability: `navigator.share({ files:[png] })` when supported (mobile), else "Download image" (canvas → PNG blob) + "Copy summary" (a short text like "Computer science is 6.8/10 AI-exposed (Reshaped) — mix of tasks shifts, the field doesn't vanish. via Major Visualizer").
   - A11y: the trigger is a real button with `aria-label`; the generated card has a text alt/summary; keyboard-reachable; respects reduced-motion (no animated reveal).
3. Keep everything else in the card as-is; do not touch the gauge math or the occupations list.

## C. Empty-data reads as intentional, not broken (`src/design/scales.ts`, `src/components/MetersView.tsx`, `src/components/MajorDetailCard.tsx`)

Bare "—" everywhere reads as broken. Add a tiny inline chip and use it wherever a metric would otherwise render a lone em dash:
- Add `src/components/DataChip.tsx`: a `micro` pill (`bg-raised`/`bg-[--line-ish]`, `text-ink3`, hairline border, rounded-full) with an optional clock icon, e.g. `Not scored yet` (exposure) / `No data` (pay, growth). Tokens only.
- Use it in `MetersView` for the exposure cell (`fmtExposure` → '—') and any '—' meter value, and in `MajorDetailCard`'s `Stat` when the value is '—' (pay/growth/exposure). In `HeatmapGrid`, leave the color tiles alone (a `NULL_FILL` tile is already the intentional treatment) — this is about the text dashes in lists/cards, not the heatmap cells.
- Never fabricate a value; the chip states the fact ("not scored yet").

## D. Quieter family filters (`src/components/HeatmapGrid.tsx`)

Today `fams` initializes to ALL families selected, and a selected chip is `bg-ink text-page` — so all eight chips render solid black and fight the data. Fix the default read:
- When every family is selected (`fams.size === allFamilies.length`) treat it as "no filter" and render ALL chips in the QUIET style (outline: `border-line bg-surface text-ink2`), since nothing is actually narrowed.
- Only once the user narrows to a subset do the still-active chips take the filled `bg-ink text-page` emphasis and the excluded ones stay quiet. The existing "Reset" affordance stays.
- Keep `aria-pressed` accurate to actual membership regardless of styling. Sentence-case is fine to keep via `.micro` uppercasing; the change is weight/fill, not casing.

## Acceptance checks (A–D)

- `exposureBand` always appears alongside the numeric score, never alone; unscored shows "Not scored yet".
- Share works on desktop (download PNG + copy summary) and uses native share when available; the card is legible in light and dark and uses only token colors.
- No lone "—" remains in the meters list or the detail card stats — each is a labeled chip; heatmap color cells are unchanged.
- On first load of the HashTable view, the family chips read as quiet outlines (not eight black pills); filling only appears when a subset is active.
- `tsc` / `npm run build` clean; keyboard, focus rings, reduced-motion, and the pinned caveat all still pass.

---

## Optional second pass (only if you want these — flag for review first)

- Search-first payoff: on the landing, picking a major from "Find your major" should open that major's result card directly (reuse the existing `onSelectMajor` → `selectMajor(cip)` path that opens the advisor/detail), instead of only filtering the map — so the personal answer comes before the big treemap.
- View label clarity: `Explore.tsx`'s View options are `Heatmap · HashTable · Value`. "HashTable" is a CS in-joke and "Value" is vague to non-CS students. Consider `Map · Table · Rankings`, or keep the HashTable pun but add a one-line subtitle/tooltip. Owner's call — don't rename without confirming, since the pun may be intentional.
- Truncated treemap labels ("Communication and…") should surface the full name on hover/focus (title/tooltip), and tiny tiles need a clearer interactive cue (subtle hover lift) so the whole map reads as clickable.

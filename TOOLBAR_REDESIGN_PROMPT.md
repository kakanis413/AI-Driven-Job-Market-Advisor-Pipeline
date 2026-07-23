# Claude Code prompt — Explore toolbar redesign

Redesign the Explore page toolbar in `src/pages/Explore.tsx` (with `src/components/LayerToggle.tsx` and `src/components/MetersView.tsx`). Follow every hard rule and design token in `CLAUDE.md` — paper & ink neutrals, violet exposure ramp, glass only on floating surfaces, WCAG AA, `prefers-reduced-motion`. Do not introduce raw hex or default Tailwind colors; use existing tokens.

## 1. Swap the two rows — controls up, search down

Today row 1 is `Logo + search + nav` and the hairlined row 2 is `View + Color`. Reverse the roles so the controls sit next to the logo and the search moves below.

- **Row 1 (top bar):** `Logo (· Explore)` → the `View` segmented control → the `Color by` / `Sort by` segmented control → `flex-1` spacer → `NavCluster`. Give the logo and each control group real breathing room (`gap-x-5`/`gap-x-6`), never cramped.
- **Row 2 (hairlined, `border-t border-line`):** the `SearchSpotlight` on the left at a generous width (roughly `w-full max-w-[420px]`) → `flex-1` → the `Legend` (tile views) or the Value caption (Value view) trailing right.
- Remove the two separate `SearchSpotlight` instances (the desktop-top and mobile-collapse copies). One search input now, in row 2, visible at all breakpoints. On narrow screens let the row-1 controls wrap or hide labels as needed, but keep search full-width in row 2.
- Keep the `glass sticky top-0 z-40` shell and the `max-w-[1400px]` container. Update the `mapH` comment/ः math if the header height changes.

## 2. Make the Value tab consistent with Heatmap / HashTable — no layout shift

The `View` segmented control already treats all three tabs identically; keep that. The jump comes from `Color by` disappearing on the Value view. Fix it:

- In the same toolbar slot, render `Color by` (`AI exposure | Median pay`) for `map`/`grid`, and a **`Sort by` segmented control (`Pay vs. debt | Versatility`)** for `meters`. Same `Segmented` component, same size, same position — so switching tabs never reflows the bar.
- Lift the Value sort state up to `Explore.tsx` (`const [sort, setSort] = useState<SortKey>('payToDebt')`) and pass it into `MetersView` as a prop, replacing the internal `useState`. The column-header sort in `MetersView` becomes a controlled reflection of that state (headers may still show the active arrow, but the `Sort by` toggle is the primary control).
- On the right of row 2: show `Legend` for tile views, and the caption `Early-career pay per $1 of typical student debt` for the Value view — in the same trailing position, so that side doesn't shift either.

## 3. Give the Value view (`MetersView`) proper definition

Keep the full-bleed, hairline-row, no-card structure (it must align to the same left edge as the tile views). Improve the row design:

- Add a **rank column** on the left (`#`, tabular nums, `text-ink3`) so it reads as a leaderboard. New grid: `[2rem] [major] [pay-vs-debt] [versatility] [exposure]`.
- Add a trailing **exposure cell** per row: the violet exposure dot (reuse `exposureColor(mode)`) + the one-decimal score via `fmtExposure`, right-aligned. This keeps the app's AI-exposure through-line present in the Value view. Header label `Exposure`, `micro text-ink3`.
- Fix versatility so the label is a **meaningful band** — `Narrow / Moderate / Broad` from `bandOf(versatilityRank)` — not "Narrow" for every row. If `bandOf` only returns one band, correct its thresholds so the three bands actually split the range.
- Keep both meters on **neutral ink** (`bg-line` track, `bg-ink2` fill) — never the exposure/pay ramp (hard rule 5 / 2). Round every number through the `scales.ts` formatters.
- Tighten row rhythm: consistent row height, `hover:bg-raised`, visible `focus-visible` ring (2px accent, offset 2px) since rows are buttons. Sticky header keeps its `bg-page/95 backdrop-blur`.

## Acceptance checks

- Switching Heatmap ⇄ HashTable ⇄ Value causes **zero horizontal reflow** of the toolbar — View, the second control, nav, search, and the trailing legend/caption all hold their positions.
- Search sits below on its own hairlined row, full-width-ish, at every breakpoint; the top row is not crowded.
- Value view shows rank, name+family, pay-vs-debt meter, versatility band meter, and an exposure dot+score, all column-aligned to the header and left-aligned to the tile views.
- No raw hex, no default Tailwind palette, no glass on data rows. Keyboard path and reduced-motion still pass.
- `npm run build` (or `tsc`) is clean; run any existing lint.

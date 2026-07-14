# Skill: Building the AI-exposure treemap + heatmap visualization

A reusable, step-by-step recipe for the signature visualization of
major-visualizer: a hand-rolled D3 + React SVG treemap that morphs into a
heatmap grid, with a find-your-major spotlight and a bridge into the advisor
chat. Follow the steps in order; each produces something testable. Design
tokens, ramps, and hard rules referenced here are defined in `CLAUDE.md` —
this doc is the *how*, that one is the *what*.

**Core principle throughout: D3 computes, React renders.** D3 is used only as
a math library (layout, scales, interpolation). Every SVG element is JSX, so
Framer Motion can own transitions and React can own state. Never let D3 touch
the DOM.

## Step 1 — Types and data loading

1. Define the contract in `src/types.ts`: `Major`, `Occupation`,
   `Family` (7-value union), `Growth` (4-value union). No `any`.
2. Write `useMajors()` in `src/hooks/`:
   - `fetch(import.meta.env.VITE_DATA_URL ?? '/data.json')`.
   - Validate at runtime (array, required keys, exposure within 0–10); reject
     bad rows with a console warning rather than crashing the app.
   - Return `{ status: 'loading' | 'error' | 'ready', majors, retry }`.
3. Every consumer renders all three states. Loading = skeleton treemap
   (animated hairline blocks in the real layout proportions of nothing —
   use a fixed placeholder hierarchy so the reveal morphs from skeleton to
   data). Error = designed card with the failing URL and a retry button.

## Step 2 — Treemap layout (pure function)

In `src/lib/layout.ts`, a pure, memoizable function:

```ts
layoutTreemap(majors: Major[], width: number, height: number,
              weight?: (m: Major) => number): TileRect[]
```

1. Build the hierarchy: `hierarchy({ children: majors })` with
   `.sum(d => weight?.(d) ?? d.completions)` and `.sort((a,b) => b.value - a.value)`.
   Group by `family` first (two-level hierarchy) so families cluster spatially.
2. Layout: `treemap().tile(treemapResquarify).size([w, h]).paddingInner(3)
   .paddingTop(22)` — the top padding hosts the family label; `resquarify`
   keeps tile positions stable across weight changes, which is what makes the
   spotlight animation legible.
3. Return flat `TileRect[]`: `{ major, x, y, w, h, family }`, keyed by `cip`.
   The `weight` parameter is the spotlight hook (Step 6) — the layout itself
   knows nothing about selection.
4. Measure the container with a `ResizeObserver` hook; recompute on resize
   (debounced one frame). The SVG uses the measured pixel size, no viewBox
   scaling — crisp 1px hairlines matter.

## Step 3 — Color scales module

In `src/design/scales.ts`, all d3, no React:

1. `exposureScale(mode)`: `scaleSequential` over domain `[0, 10]` with
   `piecewise(interpolate('oklch'), stops[mode])` using the five stops from
   CLAUDE.md. `payScale(mode, [min, max])`: same pattern, blue stops.
2. `inkFor(fill)`: WCAG contrast of `#ffffff` and `#191817` vs the fill,
   return the winner. Used by tiles, heatmap cells, and the legend.
3. Formatters (`fmtExposure`, `fmtPay`, `fmtCount`) — the only path numbers
   take to the DOM (hard rule 1).
4. Legend data generator: 5 labeled ticks per ramp so the `Legend` component
   is dumb. Legend swaps with a 250ms crossfade + axis relabel when the layer
   toggles; the tiles themselves re-color via Framer Motion `animate` on
   `fill` (400ms) so the layer change reads as a repaint, not a re-render.

## Step 4 — Rendering the treemap

`Treemap.tsx` renders one `<motion.g>` per tile, keyed by `cip`:

1. Each tile: `<motion.rect>` animated on `x/y/width/height` with the spring
   from CLAUDE.md (`stiffness 260, damping 32`) — animate SVG attributes
   directly, do **not** use Framer's `layout` prop on SVG (it assumes CSS
   layout). One spring config everywhere so morphs feel like one system.
2. Tile anatomy: fill from the active scale, 4px radius, and a 1.5px inset
   stroke in the surface color so adjacent tiles read as separate (the
   "2px surface gap" rule, achieved by stroke because rect gaps come from
   `paddingInner`).
3. Labels: render name + score only when they fit (`w > 72 && h > 40`;
   score-only when `w > 44 && h > 28`; nothing below). Ink from `inkFor`.
   Family headers sit in the 22px `paddingTop` band in `micro` type.
4. Load reveal: tiles mount with `initial={{ opacity: 0, scale: 0.96 }}`,
   stagger 14ms by descending area, capped at 450ms total.
5. Interaction: each tile is a focusable `<g role="button" tabIndex={0}>` with
   an `aria-label` ("Computer science, exposure 9.0 out of 10"). Hover/focus:
   1.5px accent ring + tooltip. Click/Enter: select → detail card + advisor
   seed (Step 7). Arrow keys move focus in layout order.
6. Tooltip: one shared `Tooltip.tsx` portal, positioned from the hovered
   tile's rect (flip near edges), showing major, exposure/10, pay, completions,
   and the `rationale` line. 150ms fade/4px rise; `pointer-events: none`.

## Step 5 — Heatmap grid (the second hero)

`HeatmapGrid.tsx` shares data, scales, tooltip, and — critically — tile keys
with the treemap, so the view toggle is a **morph**: the same keyed
`<motion.rect>`s animate from treemap rects to grid cells.

1. Geometry: rows = majors, columns = metrics (Exposure, Median pay,
   Completions, Growth), each column normalized to its own scale. Row labels
   left-aligned in `small` type; column headers in `micro` caps. Cell = rounded
   rect with the metric value **printed in the cell** (hard rule 2) in
   `inkFor` ink.
2. Sorting: clicking a column header re-sorts rows; rows animate to their new
   y with the shared spring, header shows an ▲/▼ glyph. Family filter chips
   above the grid animate exits/entries via `AnimatePresence`.
3. Crosshair: on cell hover, tint the row (a soft wash the full row width) and
   the column header; show the shared tooltip. Implement as two absolutely
   positioned motion rects that spring to the hovered row/col — one crosshair
   object that *travels*, not per-cell highlights that blink.
4. Reveal: on entering the view, cells cascade a fill from 0→value along each
   row (staggered 8ms/row, 250ms) so the grid "prints" itself.
5. The treemap⇄heatmap toggle animates in one pass: rect geometry springs to
   the cell geometry while fill cross-interpolates to the column scale. Never
   unmount one view to mount the other — same elements, new coordinates.

## Step 6 — Find-your-major spotlight

`SearchSpotlight.tsx` + the `weight` hook from Step 2:

1. Search input filters as you type (match on major + family, diacritic- and
   case-insensitive). Non-matching tiles animate to 0.25 opacity and
   desaturated fill; matching tiles keep full color. Color is not the only
   signal: matched labels stay, dimmed tiles lose their labels.
2. Selecting a result (click/Enter) sets `selectedCip` and passes
   `weight = m => m.cip === selectedCip ? m.completions * 3 : m.completions`
   into `layoutTreemap`. Because the tiling is `resquarify` and every rect is
   a keyed spring, the selected major **physically grows** and the whole map
   re-flows around it — the spotlight is a re-layout, not a zoom hack.
3. Simultaneously: dim non-selected tiles to 0.35, draw a 2px accent ring
   around the spotlit tile, and open `MajorDetailCard` (Step 7).
4. Escape or clearing the search resets weight to `completions` and springs
   everything home. In heatmap view, spotlight instead scrolls to and tints
   the row with the same ring treatment.

## Step 7 — Detail card + advisor bridge

1. `MajorDetailCard.tsx` slides in (`AnimatePresence`, 400ms) with: name,
   family badge, an SVG **exposure gauge** (180° arc, needle animated with the
   shared spring, ramp-colored track with the numeric score at center),
   pay/completions/growth stat row, `rationale`, and the mapped occupations
   list (each with its own mini exposure bar + score).
2. "Ask the advisor about this major" (and plain tile click) opens
   `AdvisorPanel.tsx` in a split-screen: viz compresses to ~60% width
   (spring — the treemap re-layout on resize doubles as the transition),
   panel takes ~40%; on mobile the panel is a full-height bottom sheet.
3. The chat is pre-seeded: a system-style header chip showing the selected
   major, and a drafted first message ("What does an exposure of 9.0 mean for
   Computer science?") the user can send or edit.
4. Transport in `src/lib/advisor.ts`: `POST VITE_AGENT_URL` with
   `{ major, cip, message }`; when unset, an async echo handler with a fake
   600ms latency and an "offline preview" badge in the panel so mock mode is
   never mistaken for a real advisor. Failures render a designed retry bubble.
5. The exposure caveat (CLAUDE.md hard rule 4) is pinned in the panel header —
   it scrolls with nothing.

## Step 8 — Verify before calling it done

- Both ramps at every stop: printed ink passes 4.5:1 (`inkFor` has tests or a
  dev-mode assertion).
- Keyboard-only walk: tab to a tile → arrow around → Enter → detail card →
  advisor → Escape home. No focus traps, focus visibly returns to the tile.
- `prefers-reduced-motion`: all springs collapse to ≤ 150ms fades.
- Resize 375px → 1440px: treemap re-lays-out, heatmap becomes horizontally
  scrollable with sticky row labels, split-screen becomes bottom sheet.
- Throttle the network: skeleton → data morph plays; kill the data URL: error
  state with retry works.

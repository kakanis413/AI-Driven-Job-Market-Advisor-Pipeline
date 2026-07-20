# major-visualizer

An interactive visualizer of how exposed US college majors are to AI, with a
conversational advisor panel. Treemap-first (inspired by Andrej Karpathy's Job
Market Visualizer), majors instead of occupations. The quality bar is an
award-winning frontend — every view must look designed, not generated.

## The four pillars

1. **AI-exposure heatmap** — every major scored 0–10 for AI exposure, visible at
   a glance in a treemap (default) and a heatmap grid (first-class alternate).
2. **Real-time data & news** — the app reads a swappable `data.json`; the data
   layer is a contract, not a hardcode, so live pipelines can feed it later.
3. **AI career advisor** — a split-screen chat, pre-seeded with whatever major
   the user is exploring, posting to a pluggable agent endpoint.
4. **Grounded in public data** — the schema mirrors public sources (CIP codes,
   SOC codes, IPEDS-style completions, BLS-style pay/growth); every score ships
   with a human-readable `rationale`.

## Data contract

The app reads an array of majors from `VITE_DATA_URL` (default `/data.json`):

```jsonc
[{
  "cip": "11.0701",              // CIP code, string
  "major": "Computer science",   // display name, sentence case
  "family": "STEM",              // one of: STEM | Business | Health | Social sci | Humanities | Arts | Trades
  "completions": 200000,         // annual degree completions (tile area)
  "exposure": 9.0,               // AI exposure 0–10 (one decimal)
  "median_pay": 99000,           // USD, early-career median
  "growth": "faster",            // "declining" | "slower" | "average" | "faster"
  "occupations": [               // mapped occupations, ordered by relevance
    { "soc": "15-1252", "title": "Software developers", "exposure": 9 }
  ],
  "rationale": "Core tasks like coding and analysis are where AI advances fastest."
}]
```

TypeScript types live in `src/types.ts` (`Major`, `Occupation`, `Family`,
`Growth`) and are the single source of truth — never inline-type the data.

### Environment variables

| Var | Purpose | Unset behavior |
|---|---|---|
| `VITE_DATA_URL` | URL of the majors JSON | falls back to `/data.json` (bundled sample) |
| `VITE_AGENT_URL` | POST endpoint for the advisor chat, body `{ major, cip, message }` | mock echo handler (clearly labeled as offline mode in the UI) |

No backend lives in this repo. The advisor must degrade gracefully: unset URL →
echo mode; failed POST → designed error state with retry.

## Tech stack & conventions

- **Vite + React + TypeScript** (strict mode). Function components + hooks only.
- **D3 for math, React for DOM.** Use `d3-hierarchy` (`treemap`, `hierarchy`),
  `d3-scale`, `d3-interpolate` to *compute* layouts and colors; render all SVG
  through JSX. **Never** a charting library (no Recharts/visx/nivo/ECharts), and
  never let D3 own the DOM (no `.append`/`.join` selections).
- **Framer Motion** for all transitions: layout animations for tile morphs,
  `AnimatePresence` for view/detail transitions, springs for spatial movement.
- **Tailwind CSS**, themed entirely from the design tokens below via
  `tailwind.config` extension + CSS custom properties. If a value isn't a token,
  it doesn't ship. No default Tailwind palette colors (`bg-blue-500` is a bug).

### Structure

```
src/
  types.ts               // data contract types
  design/
    tokens.ts            // colors, spacing, type, motion — the only source of raw values
    scales.ts            // d3 color scales (exposure, pay), ink-picker, formatters
  hooks/                 // useMajors (fetch/parse/validate), useTheme, useMediaQuery
  lib/                   // pure helpers: treemap layout, advisor client (real + echo)
  components/
    Treemap.tsx  HeatmapGrid.tsx  LayerToggle.tsx  SearchSpotlight.tsx
    MajorDetailCard.tsx  AdvisorPanel.tsx  Tooltip.tsx  Legend.tsx
  App.tsx                // view state machine + split-screen shell
```

### Naming & style

- Components `PascalCase.tsx`, hooks `useThing.ts`, helpers `camelCase`.
- One component per file; co-locate tiny private subcomponents in the same file.
- State for "what the user is looking at" (view, layer, selected major, query)
  lives in `App.tsx` and flows down as props — no state library.
- Comments only for non-obvious constraints (e.g. why a layout is memoized).

### Commit style

Conventional commits: `feat(treemap): …`, `fix(a11y): …`, `docs: …`,
`refactor: …`, `chore: …`. Imperative, ≤ 72-char subject.

## Design system

Warm "paper & ink" neutrals so the data colors are the only saturated thing on
screen. All tokens are defined once in `src/design/tokens.ts` and mirrored as
CSS custom properties on `:root` / `.dark`.

### Surfaces & ink

| Role | Light | Dark |
|---|---|---|
| Page plane | `#f4f3ef` | `#0d0c0b` |
| Surface (cards, viz) | `#faf9f6` | `#141312` |
| Raised surface | `#ffffff` | `#1c1b19` |
| Ink primary | `#191817` | `#f4f3ef` |
| Ink secondary | `#5a5852` | `#b9b6ac` |
| Ink muted (axes, meta) | `#8b887f` | `#85827a` |
| Hairline border | `rgba(25,24,23,.10)` | `rgba(244,243,239,.10)` |
| Accent (interactive, focus) | `#2a78d6` | `#5598e7` |

**Glass** (`GLASS` in `tokens.ts`, `.glass` utility in `index.css`) — for
surfaces that **float over content**: the app header, the sticky Explore
toolbar, the chat panel, the tooltip, the detail card. `backdrop-filter:
blur(16px) saturate(1.4)` — the `saturate` keeps the violet ramp from going
muddy behind the blur. Always ships an `@supports not (backdrop-filter…)`
opaque fallback so text never lands on a transparent background; text on glass
must clear 4.5:1 against the **lightest** possible backdrop, not the average.
One hairline border, no glow, no inner shadow, at most **two** stacked glass
layers (header + one panel). Never on tiles, cells, or anything encoding data.

| Role | Light | Dark |
|---|---|---|
| Glass surface | `rgba(250,249,246,.72)` | `rgba(20,19,18,.68)` |
| Glass border | `rgba(25,24,23,.08)` | `rgba(244,243,239,.10)` |

### Color ramps (data)

Both ramps interpolate through fixed stops in OKLab (hand-rolled in
`scales.ts` — d3-color has no OKLab); dark mode is its **own selected set of
stops**, never a CSS filter or auto-flip. Contrast figures below are computed,
not eyeballed.

**Exposure ramp** — "violet depth": pale lilac (low) → deep violet (high),
domain 0–10. Violet is deliberate: exposure is a MAGNITUDE, not a verdict — red
would read as danger (contradicting the pinned caveat that high exposure does
NOT mean the job disappears) and green as "safe". Violet carries neither
valence, reading as intensity, and stays clearly distinct from the
sequential-blue pay ramp so the layer toggle is unmistakable. Luminance is
monotonic, so the ramp survives color-vision deficiency without relying on hue.
The five stops sit at domain positions `[0, 0.42, 0.6, 0.76, 1]`
(`EXPOSURE_POSITIONS`), widening the hot 5–8 band where most majors fall:

| Stop (low→high) | Light | Dark |
|---|---|---|
| 0 | `#efe9f3` | `#2b2338` |
| 1 | `#d5c8e4` | `#463862` |
| 2 | `#b09ccc` | `#69538f` |
| 3 | `#8567ab` | `#9078bb` |
| 4 | `#432c63` | `#c3b2dd` |

**Pay ramp** — sequential blue, domain = min→max `median_pay`. Light mode runs
light→dark `#cde2fb → #9ec5f4 → #5598e7 → #2a78d6 → #1c5cab → #0d366b`; dark
mode flips the anchor (near-zero recedes into the surface):
`#123055 → #1c5cab → #2a78d6 → #5598e7 → #9ec5f4 → #cde2fb`.

**Tile ink is computed, never fixed.** No single text color survives either
ramp. `scales.ts` exports `inkFor(fill)`: compute WCAG contrast of ink-light
(`#ffffff`) and ink-dark (`#191817`) against the fill and return the winner
(verified ≥ 4.5:1 at every ramp stop, e.g. near-black on `#d5c8e4` = 11.15,
white on `#8567ab` = 4.64).

### Typography

One family: **Instrument Sans** (variable, self-hosted via
`@fontsource-variable/instrument-sans`), fallback `system-ui`. Hierarchy comes
from size/weight/tracking, not from a second face. All data figures use
`font-variant-numeric: tabular-nums`.

| Token | Size / line | Weight | Tracking | Use |
|---|---|---|---|---|
| `display` | clamp(2.25rem, 5vw, 4rem) / 1.05 | 640 | −0.03em | hero headline |
| `title` | 1.5rem / 1.2 | 600 | −0.02em | view titles, detail card |
| `heading` | 1.125rem / 1.35 | 600 | −0.01em | panel headers |
| `body` | 0.9375rem / 1.55 | 400 | 0 | prose, chat |
| `small` | 0.8125rem / 1.45 | 450 | 0 | tooltips, meta |
| `micro` | 0.6875rem / 1.3 | 560 | +0.08em, uppercase | axis labels, legend, badges |

### Spacing & radii

4px base scale: `4 8 12 16 24 32 48 64 96` (Tailwind `space-1…space-24`
mapped to these only). Radii: `4px` (tile), `8px` (controls), `12px` (cards),
`20px` (panels). Hairline borders at 1px, never 2px.

### Motion principles

Motion **teaches** — it shows where things went, never decorates.

- **Durations**: 150ms (hover/focus), 250ms (controls, tooltip), 400ms (view
  morphs), 700ms budget for the load reveal. Ease: `cubic-bezier(.22,1,.36,1)`.
- **Spatial moves are springs**: Framer Motion `spring, stiffness 260,
  damping 32` for tile position/size — used by the spotlight re-layout and the
  treemap ⇄ heatmap morph (tiles travel to their grid cells; never a crossfade).
- **Load reveal**: tiles animate in with a 14ms stagger ordered by area
  (biggest first), opacity + 0.96→1 scale. Total stagger capped at 450ms.
- **Sequence teaches order**: background settles before foreground. On the
  landing the ambient map (the product itself) fades in first, *then* the copy
  rises over it — the headline is one calm fade+rise (~600ms), never a
  per-word/slot-machine reveal (decoration with no informational purpose).
- **`prefers-reduced-motion`**: every layout animation collapses to a ≤ 150ms
  opacity crossfade. This is a hard requirement, not a nice-to-have.

### Dark mode

Class strategy (`.dark` on `<html>`), synced to `prefers-color-scheme` with a
manual toggle persisted to `localStorage`. Both modes are first-class: every
ramp, ink, and hover state has a selected dark value in `tokens.ts`. Never
`opacity`-fade colors to fake a dark variant.

## Hard rules (enforced in review, no exceptions)

1. **Every displayed number is rounded** through the formatters in `scales.ts`:
   exposure to one decimal ("7.5 / 10"), pay to the nearest $1k ("$99k"),
   completions compact ("200k", "1.2k"). Raw floats never reach the DOM.
2. **Color is never the only signal.** Exposure is always paired with the
   numeric score (tile label, tooltip, heatmap cell text, detail gauge);
   selection/highlight pairs color with a ring + text state.
3. **WCAG AA.** Text ≥ 4.5:1 (≥ 3:1 for large), tile ink via `inkFor`, visible
   focus rings (2px accent, offset 2px) on every interactive element, full
   keyboard path (tiles are focusable, arrow-key navigable), sensible ARIA
   (`figure`/`img` roles + labels on viz, live region for chat).
4. **The caveat is always visible:** *"High exposure does NOT mean the job
   disappears — it means the mix of tasks is likely to change."* Pinned in the
   app shell (footer bar). The advisor panel may land it once per session then
   collapse to an ⓘ — the footer copy is what satisfies this rule, so it must
   never be hidden behind a tooltip, scroll, or dismissal.
5. **Glass is for floating surfaces only.** Header, sticky toolbar, chat panel,
   tooltip, detail card — surfaces that float over content. **Never** on tiles,
   heatmap cells, or any element that encodes data: translucency corrupts the
   color encoding. Body-text surfaces don't get it either (a legibility tax
   with no upside).
6. **Advisor voice: lead with the answer.** No preamble, no restating the
   question, no "great question / it is wonderful". The first sentence carries
   the number or the verdict; 2–3 tight paragraphs, ≤3 sentences each. Keep the
   exposure-≠-job-loss framing present but not as the opener every time.

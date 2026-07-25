# Claude Code prompt — bigger treemap + make small families (Trades) legible

Two changes to the Explore treemap. Read `src/lib/layout.ts`, `src/components/Treemap.tsx`, `src/pages/Explore.tsx`, and the treemap/`TILE AREA` notes in `CLAUDE.md` first.

## The problem (already diagnosed — don't re-investigate)

Tiles are sized by graduates (`layoutTreemap` `.sum(completions)`). Trades is genuinely ~0.5% of all graduates (~11,300 of 2.15M, across 15 tiny majors), so its family band is a sub-70px sliver — narrow enough that even the "TRADES" label (gated on `b.w > 70` in `Treemap.tsx`) never renders. A bigger map alone won't fix it; 0.5% stays a sliver.

## 1. Minimum legible tile size (the Trades fix)

In `layoutTreemap` (`src/lib/layout.ts`), apply a floor to each major's layout weight so the smallest tiles reach a clickable minimum, while large tiles stay proportional to each other:

- Compute an adaptive grad-floor from the map area, not a magic number: target a minimum tile of ~44×30px. `floor = (targetMinPx² / (width*height)) * totalCompletions`, where `totalCompletions` is the sum across the majors being laid out. This keeps the "minimum legible size" consistent across viewports and datasets.
- Use `Math.max(completions, floor)` as the value in `.sum(...)` (keep the `spotlightCip` ×3 behaviour composing with the floored value). Large tiles (tens of thousands of grads) are far above the floor and keep their exact relative sizing; only sub-floor majors get lifted.
- This runs through the one `layoutTreemap` used by `Treemap`, `HeatmapGrid` morphs, and `Landing`, so all three stay consistent — verify the cross-view morph still lines up.
- Result to expect: the Trades band becomes a small but visible, clickable cluster with its label showing; big families barely move.

Honesty about the encoding (CLAUDE.md "tile area = bachelor's grads"): area is now approximate for the smallest majors. Update the caption in the Explore toolbar from `TILE AREA = BACHELOR'S GRADS` to something like `TILE AREA ≈ GRADUATES · SMALL MAJORS SIZED UP TO STAY LEGIBLE` (keep it in the existing `micro` token style), and add a one-line comment in `layout.ts` explaining the floor and why (legibility vs strict proportionality). Do not change the numeric data or `data.json` — this is a layout-only floor, never a data mutation.

## 2. A little bigger

In `src/pages/Explore.tsx`, give the map more vertical room modestly: raise the floor and reduce the chrome subtraction in `mapH` (currently `Math.max(480, vh - 190)`) to about `Math.max(520, vh - 168)`, and trim the `main`'s top margin (`mt-3` → `mt-2`) if it helps without crowding the toolbar. Keep it within the viewport — no page scroll introduced on a normal laptop height. Don't touch the sticky glass chrome or the pinned footer caveat.

## Guardrails / acceptance

- Trades renders as a visible, labelled, clickable family band; welding-scale majors are at least ~44px and reachable by pointer and keyboard.
- Large tiles keep their relative proportions (Business still dominant, CS still large); the floor only lifts the smallest tiles.
- Cross-view morph (treemap ⇄ heatmap), spotlight re-layout, load-reveal stagger, tooltips, focus rings, and reduced-motion all still work.
- The area caption now honestly reflects the min-size floor; no raw hex / default Tailwind; `tsc` / `npm run build` clean.

## One decision to confirm before shipping

The min-size floor intentionally trades strict area accuracy for legibility at the small end. If the team would rather keep area 100% honest, the alternative is to leave the treemap exact and instead make small families reachable another way (e.g. a family filter / "jump to Trades" control) — but that does not make Trades visually bigger, which was the request. Default to the floor unless told otherwise.

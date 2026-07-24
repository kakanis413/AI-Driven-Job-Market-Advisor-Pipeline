# Handoff Spec: Treemap family drill-down ("focus mode")

## Overview

The Explore treemap shows every major at once, grouped by family. Large families
(STEM, Social Sci, Business) have a long tail of small programs that collapse into
a strip of tiny, unlabeled, un-tappable tiles — impossible to read or explore,
especially on touch.

**Proposal:** collapse each family's long tail into one **"+N more" aggregate
tile**. Tapping it (or the family label) enters **focus mode** — the treemap
re-lays out to show *only that family*, filling the whole canvas, so every program
becomes a large, labeled, tappable tile. A back control returns to the all-families
overview. This is a subtree zoom, not a new screen.

Two levels of navigation:

1. **Overview** — all families, each capped to its legible tiles + one "+N more".
2. **Focus** — one family, all its majors, edge-to-edge, readable.

---

## Layout

**Overview (unchanged grid), with one addition per family**
- Reuse the existing two-level layout in `src/lib/layout.ts`
  (`hierarchy` → `treemap(treemapResquarify)`), padding tokens as tuned
  (`paddingInner` 6 / 1.5, `paddingTop` 22).
- **Per family**, after sizing, keep the majors whose computed tile clears the
  legible threshold (`w > 78 && h > 46`, the existing `showName` gate). Sum the
  remaining tail into **one synthetic leaf** `{ rest: true, family, count, value:
  Σ completions }`. Render it as the last tile in the band.
- If a family's tail is 0–1 hidden majors, render them normally — **no aggregate
  tile** (an aggregate that hides one item is worse than showing it).

**Focus mode**
- Call the same `layoutTreemap(majorsInFamily, width, height)` with the majors
  filtered to the focused family. One band, full canvas. The family label strip
  is replaced by the breadcrumb bar above the viz (below), so `paddingTop` for the
  single band drops to `0` in focus mode.
- Focus canvas uses the **same width/height** as the overview viz
  (`vizW`, `mapH` in `Explore.tsx`), so the zoom morph stays in one plane.

---

## Design tokens used

| Token | Value | Usage |
|---|---|---|
| `--radius-tile` | 4px | Aggregate tile + all tiles |
| `space-2 / space-4` | 8 / 16px | Breadcrumb padding, back-button gap |
| exposure ramp (`EXPOSURE_STOPS`) | current ramp | Aggregate tile fill = family's **mean** exposure |
| `--ink` / `inkFor(fill)` | computed | Aggregate label ink (same contrast rule as tiles) |
| `micro` type token | 0.6875rem, +0.08em, upper | "+N MORE" label, breadcrumb crumb |
| `SPRING` | stiffness 260, damping 32 | Zoom in/out tile morph |
| `REDUCED_TWEEN` | 150ms opacity | Reduced-motion replacement |
| `EASE` | cubic-bezier(.22,1,.36,1) | Breadcrumb fade, dim |

No new raw values. The aggregate tile is a data tile (never glass).

---

## Components

| Component | Variant | Props | Notes |
|---|---|---|---|
| `AggregateTile` (new, in `Treemap.tsx`) | overview only | `family, count, fill, rect` | Fill = mean exposure of the tail so it still encodes; label "**+N more**" + family. Tap → `onFocusFamily(family)` |
| `Treemap` | `mode="overview" \| "focus"` | add `focusedFamily`, `onFocusFamily` | In focus, receives pre-filtered majors; hides the aggregate tile |
| `FocusBreadcrumb` (new) | — | `family, onBack` | "All majors ‹ **STEM**" with a back button; sits above the viz, left-aligned |
| `Explore` | — | add `focusedFamily` state | Owns focus state; filters majors; passes down |

Aggregate tile content rules:
- ≥ 78×46px available → "**+N more**" (micro, ink via `inkFor`) + family caption.
- Smaller → show just "**+N**" centered; full label in the tooltip/aria-label.

---

## States and interactions

| Element | State | Behavior |
|---|---|---|
| Aggregate tile | Default | Fill = family mean exposure; subtle inner "stack" motif (2px offset ghost rect at 40% opacity) to read as "a group, not a major" |
| Aggregate tile | Hover / focus-visible | Accent ring (2px `--accent`, offset 2), tooltip: "N more <family> majors — open to explore" |
| Aggregate tile | Tap / Enter / Space | Enter focus mode for that family |
| Family label | Tap / Enter | Same as aggregate tile — enters focus for that family (whole label is a button) |
| Tile (in focus) | Tap | Existing behavior — select → open advisor/detail |
| Breadcrumb "All majors" | Tap / Enter | Exit focus → overview |
| Anywhere | `Esc` | Exit focus first; if already overview, fall through to existing clear-selection/search (extend the `Escape` handler already in `Explore.tsx`) |
| Search box | Type while focused | Either (a) auto-exit focus and filter globally, or (b) filter within the family. **Recommended: exit focus** — search is a global action; show the match-count toast |

---

## Responsive behavior

| Breakpoint | Changes |
|---|---|
| Desktop (>1024px) | Overview default; drill-down is a convenience |
| Tablet (768–1024) | Same; aggregate tiles appear sooner (more tails hidden) |
| Mobile (<768px) | **Drill-down is primary.** Overview tiles are tiny, so the aggregate "+N more" is the main way in. Consider defaulting Explore to focus-on-tap and/or the Table view. Back control must be thumb-reachable (top-left breadcrumb + `Esc`/system-back on Android) |

Because tile count per family scales with viewport, compute the "legible" cutoff
from the *actual* laid-out `w/h`, not a fixed K — so the aggregate absorbs
exactly what wouldn't have rendered a label.

---

## Edge cases

- **Family with ≤ 1 hidden major** → no aggregate tile; render normally.
- **Family with only tiny majors** (all below threshold) → aggregate shows the
  whole family count; tapping still drills in and they become readable.
- **Focus on a family with 1 major** → fills canvas as one tile; back still works.
- **Spotlight/search active** → aggregation is disabled while a query dims tiles
  (don't hide a matched major inside "+N more"); or surface matched tail majors.
- **Deep-link / route** → optionally encode focus in the hash
  (`#/explore/family/STEM`) so it's shareable and survives reload; otherwise focus
  is ephemeral state (fine for v1).
- **Empty data / loading** → aggregate logic runs only on `status === 'ready'`;
  skeleton unchanged.
- **Long family names** in breadcrumb → truncate with ellipsis at container width.

---

## Animation / motion

| Element | Trigger | Animation | Duration | Easing |
|---|---|---|---|---|
| Tiles → focus | Tap aggregate/label | Focused family's tiles **grow to fill** the canvas; other families fade + scale to 0.96 | spring | `SPRING` (260/32) |
| Tiles → overview | Back/Esc | Reverse: focused tiles shrink back to their band slot; others fade in | spring | `SPRING` |
| Breadcrumb | Enter/exit focus | Fade + 4px rise | 250ms | `EASE` |
| Aggregate tile | Idle | None (motion teaches; no decoration) | — | — |
| Reduced motion | any | Replace morph with ≤150ms opacity crossfade | 150ms | `REDUCED_TWEEN` |

**Reuse the existing morph infra:** you already snapshot tile geometry in
`geomRef` and animate tiles from prior rects (treemap ⇄ heatmap). Drive the
zoom the same way — Framer `layout`/`initial` from the tile's overview rect to its
focus rect — so it reads as one continuous re-layout, never a crossfade.

---

## Accessibility notes

- **Aggregate tile** is a `role="button"`, `tabIndex={0}`,
  `aria-label="N more <family> majors. Press Enter to explore this family."`
  Keyboard: Enter/Space drills in; it joins the existing arrow-key tile order.
- **Focus mode entry** moves keyboard focus to the breadcrumb's back button (or
  the first tile) so keyboard/SR users aren't stranded; **exit** restores focus to
  the tile/aggregate that opened it (mirror the `restoreRef` pattern in
  `UniversityGateModal.tsx`).
- **Breadcrumb** is a `<nav aria-label="Treemap location">` with the back control
  as a real `<button>`. Announce focus changes via the existing viz live region.
- `Esc` exits focus (extend the current handler), matching the app's escape ladder.
- Aggregate tile still pairs color with text ("+N more"), satisfying the
  "color is never the only signal" rule.

---

## Suggested build phases

1. **Aggregate tile** in `layout.ts` + `Treemap.tsx` (static "+N more", tap logs).
2. **Focus state** in `Explore.tsx` (filter majors, breadcrumb, back, Esc).
3. **Morph** (reuse `geomRef`) + reduced-motion path.
4. **A11y polish** (focus move/restore, aria, live region) + mobile defaults.
5. Optional: **hash routing** for shareable focus.

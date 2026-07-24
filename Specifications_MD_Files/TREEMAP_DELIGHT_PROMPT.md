# Claude Code prompt — treemap hover-lift (+ optional landing payoff reroute)

Small frontend polish. Most of what looks missing is already handled — do NOT re-add it:
- Truncated tile labels already surface the full name via the `Tooltip` on hover AND keyboard focus (`onTip` in `Treemap.tsx` / `Landing.tsx`). Leave that alone.
- Tiles already show a hover/focus/selected ring and a pointer cursor, including sub-threshold tiles. Keep it.
- Landing search already opens a major's card (`onSelectMajor` → `selectMajor` → Explore `initialSelectedCip`). Don't rebuild it.

Stay within `CLAUDE.md`: motion teaches, springs for spatial moves (`SPRING` from tokens), `prefers-reduced-motion` disables the lift entirely, tokens only, WCAG AA and focus rings unchanged.

## 1. Tactile hover-lift on treemap tiles (`src/components/Treemap.tsx`)

Today a tile's only hover feedback is the flat ring — it reads static. Add a subtle lift so the map feels alive and clearly interactive:
- In `TileView`, on hover OR keyboard focus (not on the dimmed/unmatched tiles), animate a gentle scale up (~1.015–1.02) and a slight raise. Because tiles are SVG `<g>` positioned by `x`/`y`, do the lift with `scale` on the existing `motion.g` `animate` (compose with the current `x/y/opacity/scale` so morphs and the load-reveal still work), or a 1px `y` nudge — whichever keeps the spring clean. Keep the existing ring.
- Use the existing `spr` spring; keep it fast and quiet (this is a hover state, ~150ms feel). Never let the lift fight the cross-view morph or the load-reveal stagger.
- `prefers-reduced-motion`: no scale/raise at all — the ring alone remains the cue (already the case).
- Do not change dimming, selection, tooltip, keyboard nav, or ARIA.

Apply the same treatment to the landing results tiles (`ResultsMap` in `src/pages/Landing.tsx`) so hover feel is consistent between the two treemaps. Leave the faint non-interactive `TextureMap` untouched.

## Acceptance

- Hovering or keyboard-focusing a tile gives a subtle spring lift + the existing ring; leaving returns it cleanly; dimmed/unmatched tiles don't lift.
- Cross-view morph (treemap ⇄ heatmap), load-reveal stagger, selection ring, and tooltips all still work.
- Reduced-motion shows no lift. `tsc` / `npm run build` clean; focus rings and the pinned caveat unchanged.

---

## Optional — landing picks open /chat instead of the Explore panel (decide first)

Currently picking a major on the landing opens a ~400px card over the full treemap on Explore. Now that `/chat` exists as the roomy result+advisor home, you MAY reroute landing picks there for a stronger first payoff:
- Change the landing's `onSelectMajor` handler in `src/App.tsx` to `nav('chat', cip)` (Chat already accepts `initialCip={sub}`) instead of `selectMajor(cip)`.
- Trade-off: `/chat` is focused and roomy but drops the map-as-context; the Explore panel keeps the map visible behind the card. Only make this change if you want the focused payoff — otherwise leave landing → Explore as-is. Do not change both; pick one.

# UI redesign — critique & work order

**For:** Claude Code · **Status:** plan, nothing implemented
**Scope:** Explore page density, chat panel, landing page, and a disciplined glass system.

---

## 0. Overall impression

The visual craft is good — type, spacing and restraint all read as designed rather than
generated. Three things hold it back:

1. **The Explore page spends ~26% of the viewport before showing any data**, on a page whose
   entire job is showing data.
2. **The chat panel is mostly empty space wrapped around an unstructured wall of text** — and
   the text problem is a prompt bug, not a layout bug.
3. **The landing page is a well-executed template.** Eyebrow → giant headline → subhead → two
   CTAs → stat row is the default SaaS hero. Nothing about it could only belong to *this*
   product, even though this product has a genuinely distinctive asset sitting right there.

---

## 1. Explore page — reclaim the map

### The space budget (measured from the screenshot, ~1519px tall viewport)

| Band | Height | Earning its space? |
|---|---|---|
| App header | ~104px | Yes — nav + mode toggle |
| "Explore the map" + subtitle | ~140px | **No.** Restates the tab you just clicked |
| Toolbar card (padding + controls) | ~120px | Controls yes, the padding no |
| **Total before data** | **~364px (24%)** | |

The treemap then runs off the bottom edge — the densest content gets the leftovers.

### Findings

| Finding | Severity | Fix |
|---|---|---|
| Page title + subtitle duplicate the active nav tab | 🔴 | **Delete both.** Fold the one useful sentence ("Tiles sized by graduates") into the legend as micro text |
| Toolbar is a floating card with card padding | 🟡 | Convert to a **sticky glass bar** directly under the header. One row, ~56px |
| Treemap is clipped at the viewport bottom | 🟡 | Once the above is done the map gets ~200px back; give the container `min-h-[calc(100dvh-160px)]` |
| Tiny tiles render meaningless acronyms — `SSAT`, `ECMGAGS`, `IRANSS`, `BBAMB` | 🔴 | Below a size threshold render **no label at all**. An unreadable acronym is worse than an empty tile — it looks broken. Name appears on hover/focus |
| Legend sits far right, detached from the map it explains | 🟢 | Keep it in the sticky bar, right-aligned — fine once the bar is one row |

### Target layout

```
┌─ header (glass, sticky) ─────────────────────────────┐  ~64px
├─ toolbar (glass, sticky): search · view · color · legend ┤  ~56px
└─ treemap — everything else ──────────────────────────┘  ~85% of viewport
```

---

## 2. Chat panel

### The real problem is upstream

The reply in the screenshot opens: *"It is wonderful to connect with you to discuss your
interest in Psychology, General. You asked about what an AI exposure score of 5.0/10 means for
this path…"* — two sentences of filler restating the question before any information. Then
`$43,757` arrives buried mid-paragraph.

**No UI change fixes this.** Update the advisor instruction in `advisor/agents.py`:
- No preamble, no restating the question, no "it is wonderful/great question."
- **Lead with the answer.** First sentence carries the number or the verdict.
- Short paragraphs (≤3 sentences). Prefer 3 tight paragraphs over 5 loose ones.
- Keep the exposure-≠-job-loss framing, but it can't be the opener every time.

### UI findings

| Finding | Severity | Fix |
|---|---|---|
| Messages top-anchored → large void below when short | 🔴 | Bottom-anchor the thread (`justify-end`), like every messaging UI. New messages rise from the input |
| Response overflows with no affordance that more exists | 🔴 | Scroll container + a soft fade mask at the bottom edge |
| Suggested prompts render as dark bubbles identical to sent messages | 🟡 | Style suggestions as **outlined chips** above the input — never as a sent message. Right now it's unclear whether the user asked it |
| The caveat banner is persistent and duplicates the footer caveat | 🟡 | Show it once per session, then collapse to a small ⓘ next to the LIVE badge |
| Numbers are invisible inside prose | 🟡 | After the prose, render a compact stat strip from the request payload: exposure · pay · growth. Grounded and scannable |
| Send button is a low-contrast grey circle | 🟢 | Use the ink fill (matching the landing CTA) when the field has content |
| Panel is a hard-edged white sheet over the map | 🟢 | Glass surface (§4) — it's floating over content, the ideal case |

### What already works
The LIVE badge, the staged thinking state ("Looking up occupations…"), and the per-major
header are all good. Keep them.

---

## 3. Landing page

### Why it reads generic
Eyebrow with dots → oversized headline → subhead → primary + secondary CTA → 4-stat row. That
is the default template. Meanwhile **the actual product — a live treemap of 360 majors — is
sitting in the background at near-zero opacity, doing nothing.**

The per-word slot-machine reveal is itself a played-out pattern, which is part of why the
motion "runs fast for no reason": eight words fire in sequence for no informational purpose.

### Findings

| Finding | Severity | Fix |
|---|---|---|
| Secondary CTA "Straight to the heatmap" | 🟡 | **Delete it.** Two CTAs split intent; the heatmap is one toggle away inside Explore |
| Motion is fast and unmotivated | 🟡 | Drop the per-word reveal. One calm headline fade+rise (~600ms). Let the **ambient map settle first**, then the words — motion should teach sequence, not decorate |
| Ambient treemap is invisible | 🔴 | This is your signature asset. Raise opacity so tiles are legible, and let the real exposure ramp show. It should look like the product, not wallpaper |
| Stat row is filler | 🟢 | `0–10 TASK-LEVEL EXPOSURE` isn't a statistic. Keep `360 majors` and `Live advisor`; cut the rest |
| Pointer parallax is twitchy | 🟢 | Reduce factor, increase spring damping |

### The direction: make the map the hero, not the wallpaper

Reference: **quietpress** — a full-bleed, richly colored photographic hero with small type and
**glass UI floating over it**. What makes it work isn't the photo; it's that the *product* is
center stage in full color and the copy defers to it.

Our equivalent isn't a photograph — **it's the treemap.** Today it sits behind the headline at
near-zero opacity doing nothing. Flip that relationship:

**1. Full-bleed, full-color living map.** The treemap becomes the hero surface, edge to edge, at
**full saturation** on the violet ramp — not a 8%-opacity ghost. This is the "colorful" ask, and
it's answered with our own data rather than decoration.

**2. Copy floats over it in glass.** The headline, subhead and caveat move into a **glass panel**
(§4 tokens) over the map — exactly quietpress's pattern of glass chips over rich imagery. This is
where glassmorphism earns its place: real content behind it to refract.

**3. The map is interactive on the landing page.** Hovering a tile reveals its major name;
clicking goes straight to Explore with it selected. This is the "something you'd click on, not
just words" — the hero *is* the product, so the first interaction is real rather than a CTA.

**4. A floating glass widget, bottom-right** — quietpress has a persistent player; we have the
advisor. A small glass chip ("Ask about any major →") that opens the chat, so the page feels
alive and the advisor is discoverable from the first screen.

**5. Search stays, CTAs go.** Keep the `Find your major` field (typing highlights matching tiles
in the live map behind), delete both CTA buttons.

**6. Motion earns its keep.** Tiles settle into place first, *then* the copy fades up over them.
Sequence teaches order. Drop the per-word slot-machine reveal entirely.

### ⚠️ The blocker on "colorful"

**The map cannot look colorful until exposure varies.** Every major is currently `5.0`, so the
ramp renders one flat lavender no matter how saturated we make it. Until the scoring pipeline
lands, the hero should render from a **small curated demo dataset with realistic varied
exposure** so the ramp actually shows its range. The `SAMPLE DATA` badge already keeps this
honest, and the landing is illustrative by nature.

### Headline

Team's line, to replace the current headline:

> **See how AI is integrating into your major.**

"Integrating into" is a genuine improvement over "exposed" — it describes a process rather than a
vulnerability, which is exactly the tone we want.

One note for the team: as written with a question mark (*"See how AI is integrating into your
major?"*) it's grammatically mixed — "See how…" is an instruction, not a question. Two clean
options, both fine:
- **Statement/invitation:** *See how AI is integrating into your major.* ← recommended, pairs
  naturally with the search field beneath it
- **True question:** *How is AI integrating into your major?*

Pick one; don't ship the hybrid.

---

## 4. Glassmorphism — a disciplined system

**Recommendation: adopt it, but only on floating surfaces.** Applied site-wide it would break
this product, because glass over *data* destroys contrast — and CLAUDE.md's hard rule is that
color and text must stay WCAG AA legible on every tile.

| Surface | Glass? | Why |
|---|---|---|
| App header | ✅ | Floats over the map; content scrolls beneath |
| Explore toolbar (sticky) | ✅ | Same |
| Chat panel | ✅ | Overlays the treemap — the ideal case |
| Tooltip | ✅ | Floats over tiles |
| Major detail card | ✅ | Overlay |
| **Treemap tiles** | ❌ **Never** | Tiles *are* the data. Translucency corrupts the color encoding |
| **Heatmap cells** | ❌ Never | Same |
| Body text surfaces | ❌ | Blur behind text is a legibility tax with no upside |
| Landing hero panel | ⚠️ Optional | Only if the ambient map is bright enough to be worth refracting |

### Tokens to add (`src/design/tokens.ts`)

```ts
export const GLASS = {
  light: {
    bg: 'rgba(250, 249, 246, 0.72)',
    border: 'rgba(25, 24, 23, 0.08)',
    blur: '16px',
  },
  dark: {
    bg: 'rgba(20, 19, 18, 0.68)',
    border: 'rgba(244, 243, 239, 0.10)',
    blur: '16px',
  },
} as const
```

**Rules:**
- `backdrop-filter: blur(16px) saturate(1.4)` — saturate keeps the violet ramp from going muddy.
- Always provide a **fallback**: `@supports not (backdrop-filter: blur(1px))` → opaque surface.
  Never let text land on a transparent background.
- Text on glass must still hit **4.5:1 against the lightest possible backdrop**, not the average.
- One hairline border, no double borders, no glow, no inner shadow.
- Max **two** glass layers stacked (header + panel). A third is a modal, not glass.

---

## 5. CLAUDE.md updates required

Do these as part of the work — the doc currently forbids what we're adopting.

1. **Surfaces section** — add the `GLASS` tokens and the floating-surfaces-only rule.
2. **Hard rules** — add: *"Glass is for surfaces that float over content. Never on tiles,
   cells, or any element encoding data."*
3. **Motion principles** — replace the per-word headline reveal guidance; add: *"Sequence
   teaches order: ambient/background settles before foreground copy."*
4. **Advisor voice** (new, small section) — no preamble, lead with the number, ≤3 sentences
   per paragraph.
5. Confirm the ramp table reflects the violet stops (may already be done).

---

## 6. Build order

Highest value first; each step ships independently.

1. **Explore density** — delete the title block, make the toolbar a sticky glass bar, drop
   labels on undersized tiles. *Biggest visible win, lowest risk.*
2. **Advisor prompt** — kill the preamble, lead with the answer. *One-line-ish change, huge
   perceived quality gain.*
3. **Chat panel** — bottom-anchor, scroll + fade mask, suggestion chips, stat strip, glass.
4. **Glass tokens + header/toolbar/tooltip/detail card** — with the `@supports` fallback.
5. **Landing** — remove secondary CTA, calm the motion, raise the ambient map, trim stats.
6. **Landing hero search** — the distinctive move. Do last; it's the largest change.
7. **CLAUDE.md** — update alongside, not after.

---

## 7. Guardrails (do not regress these)

- WCAG AA on every surface, including text on glass at its most transparent.
- Tile ink still resolved through `inkFor` — glass must not touch tiles.
- `prefers-reduced-motion` still collapses every layout animation to a ≤150ms fade.
- The exposure caveat stays visible somewhere at all times.
- No new tokens beyond `GLASS`. If a value isn't in `tokens.ts`, it doesn't ship.
- Keep `pytest` green and the typecheck clean.

---

## 8. Not in scope

Mobile redesign (separate pass) · the flat 5.0 exposure data (teammates' pipeline) ·
the News tab (see `NEWS_TAB.md`) · any change to the data contract.

# News — system design

**Status:** draft for team review · adjust freely
**Goal:** make the "real-time data and news tracking" pillar *visible in the product*, not just
answerable in chat.

---

## 1. Two surfaces, one system

News appears in two places, and they do different jobs:

| Surface | Job | Scope | Freshness | Cost |
|---|---|---|---|---|
| **Advisor chat** | Personalized — the user *asked* | The selected major | Live, on demand | A search per ask (justified: they asked) |
| **News tab** | Browse — discovery | Family (STEM, Business, Health…) | Precomputed + cached | 7 searches per refresh cycle |

The important design decision: **they share one data shape and one card component.** Two
surfaces, not two implementations.

### The flow

```
User (major selected) asks the advisor about news / current events
        │
        ▼
Advisor answers in prose  +  returns up to 3 grounded news items
        │
        ├── panel renders the prose
        ├── panel renders 3 NewsCards (variant="compact")
        └── panel appends: "More news for Social sci →"   ← built by the FRONTEND, not the model
                     │
                     ▼
              News tab, pre-filtered to that family
              NewsCards (variant="full"), precomputed
```

This resolves the periodic-vs-personalized tension: **periodic fetching can't know what the
user will click**, so the tab covers fixed buckets (families), while the chat handles the
specific case on demand. The link makes the tab discoverable — a tab nobody clicks is a wasted
feature; a "more like these" hand-off from an active conversation is the best entry point.

---

## 2. Data contract (shared by both surfaces)

One shape. The chat returns up to 3; the tab returns 3–5 per family.

```jsonc
{
  "family": "STEM",
  "fetched_at": "2026-07-20T14:00:00Z",
  "items": [
    {
      "title": "…",
      "source": "Reuters",          // publication name
      "url": "https://…",           // MUST come from search grounding (see §7)
      "published": "2026-07-18",    // ISO date, nullable
      "summary": "One or two sentences on why this matters for this field."
    }
  ]
}
```

**Backend response schema addition** (`advisor/schemas.py`) — the chat carries items alongside
the prose so the panel can render real cards instead of parsing text:

```jsonc
{
  "generated_guidance": "…advisor prose…",
  "news": [ /* NewsItem[], max 3, may be empty */ ],
  // existing: agent_node, status, route, degraded
}
```

---

## 3. Component: `NewsCard`

The atom. **One component, two variants** — this is the system win.

### Variants

| Variant | Use when | Shows |
|---|---|---|
| `compact` | Inside the advisor chat (max 3) | Title, source · date, external-link affordance |
| `full` | News tab | Title, source · date, summary, external-link affordance |

### Props

| Prop | Type | Default | Description |
|---|---|---|---|
| `item` | `NewsItem` | — | The news item (see §2) |
| `variant` | `'compact' \| 'full'` | `'full'` | Density; compact omits the summary |

### States

| State | Visual | Behavior |
|---|---|---|
| Default | Raised surface, hairline border, radius `12px` | — |
| Hover | Border → `border-strong`, title → accent | 150 ms, `cubic-bezier(.22,1,.36,1)` |
| Focus | 2 px accent ring, 2 px offset | Full keyboard reachable |
| Visited | Title ink → ink-secondary | Signals already-read |
| No URL | **Not rendered** | Drop the item entirely (§7) |

### Tokens (from `src/design/tokens.ts` — no new values)

- **Surface:** raised surface · hairline border · radius `12px` (card)
- **Type:** title → `body` (600); source/date → `micro` (uppercase, +0.08em); summary → `small`
- **Spacing:** `12` inner padding, `8` between title and meta, `16` between cards
- **Color:** accent for the link affordance; ink-muted for meta. **No new colors** — news is
  chrome, not data, so the ember ramp stays reserved for exposure.

### Accessibility

- Each card is a single `<a>` wrapping the content — one tab stop, not three.
- `aria-label`: `"{title} — {source}, opens in new tab"`.
- External links: `target="_blank" rel="noopener noreferrer"` + a visible external-link icon
  (never color alone — CLAUDE.md hard rule #2).
- Date rendered as `<time datetime="…">` with a human-readable label.

---

## 4. Component: `NewsList`

Renders a set of `NewsCard`s plus the surrounding states. Used by both surfaces.

| Prop | Type | Default | Description |
|---|---|---|---|
| `items` | `NewsItem[]` | `[]` | Items to render |
| `variant` | `'compact' \| 'full'` | `'full'` | Passed to each card |
| `fetchedAt` | `string \| null` | `null` | Renders "Updated {relative}" |
| `state` | `'idle' \| 'loading' \| 'error'` | `'idle'` | Drives the states below |

### States

| State | Treatment |
|---|---|
| Loading | 3 skeleton cards at card dimensions — no layout shift on arrival |
| Empty | *"No recent items for this field."* — a fact, not an error. Never fabricate to fill space. |
| Error | *"Couldn't load news."* + Retry. The rest of the page keeps working. |
| Stale | `fetched_at` always visible, so age is never hidden |

---

## 5. Page: News tab

- Added to the existing route pattern (`src/pages/`, `useRoute.ts`) alongside Explore/Landing.
- **Family selector** reuses `LayerToggle`'s visual language — do not invent a second toggle style.
- Deep-linkable: `/news?family=Social+Sci` so the chat CTA can preselect.
- The pinned exposure caveat stays in the app shell (CLAUDE.md hard rule #4) — news does not
  replace or hide it.

### Motion
- Cards fade+rise in on load, **14 ms stagger, capped at 450 ms** (matches the treemap reveal).
- Family switch: 250 ms crossfade (control-speed).
- `prefers-reduced-motion` → ≤150 ms opacity crossfade, no movement. Hard requirement.

---

## 6. Caching strategy

| Bucket | Strategy | Why |
|---|---|---|
| **Family** (7) | Precomputed, TTL 6–24 h | Cheap (7 searches/cycle), always instant, covers every major |
| **Per major** (376) | ❌ Not precomputed | 376 searches/cycle, most never viewed |
| **Per major on demand** | Lazy cache on first request, TTL | First viewer waits ~8 s; everyone after is instant. Popular majors stay warm, obscure ones cost nothing |

Endpoint: `GET /api/v1/news?family=STEM` → §2 shape, cached per family.
A scheduled refresh can replace the TTL cache later **without changing the contract**.

---

## 7. Hard rules

1. **URLs must come from Google Search grounding metadata** — never composed by the model. An
   item without a verifiable URL is **dropped, not rendered**. A hallucinated link is the same
   class of failure as an invented salary figure, and worse because anyone can click it.
2. **The frontend builds the "more news" link**, not the model. Given a selected major, the
   panel derives `/news?family={major.family}`. Models invent plausible-but-wrong routes.
3. **Never fabricate to fill space.** Empty is a valid, honest state.
4. **No new design tokens.** If a value isn't in `tokens.ts`, it doesn't ship.
5. **Freshness is always visible.** `fetched_at` renders on every surface.

---

## 8. Build order (parallelizable)

The frontend does **not** wait on the backend — same pattern that let the treemap ship before
real `data.json` existed.

1. **Agree §2** (the contract). Everything else forks from here.
2. **Frontend:** `NewsCard` → `NewsList` → News page, built against a fixture at
   `public/news.json`. Ship all states.
3. **Backend:** `GET /api/v1/news?family=` with structured output + family cache.
4. **Backend:** add `news[]` to the advisor response.
5. **Frontend:** render the 3 compact cards + the CTA in `AdvisorPanel`.
6. Swap the fixture URL for the endpoint. No UI changes.

---

## 9. Open questions

- [ ] Family grouping confirmed, or a different bucketing?
- [ ] TTL — 6 h, 24 h, or a scheduled daily job?
- [ ] Items per family (proposed 3–5) and per chat answer (proposed max 3)?
- [ ] Search phrasing per family, e.g. `"AI impact on {family} careers 2026"` — who owns tuning it?
- [ ] Per-major news in the detail card in v1, or defer?
- [ ] Who owns the endpoint — the advisor-agent owner?

## 10. Out of scope for v1

Per-major precomputation for all 376 · user-configurable feeds · sentiment/trend analysis ·
notifications · saving or sharing articles.

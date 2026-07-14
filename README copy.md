# Major Visualizer

An interactive visualizer of how exposed US college majors are to AI — a
treemap/heatmap of majors sized by graduates and colored by AI exposure, with a
find-your-major spotlight and a conversational advisor panel. Inspired by
Andrej Karpathy's Job Market Visualizer, applied to fields of study.

> **Always-on caveat:** high exposure does **not** mean the job disappears —
> it means the mix of tasks in that field is likely to change.

## Quickstart

```bash
npm install
npm run dev       # http://localhost:5173
npm run build     # typecheck + production build
```

Ships with ~24 sample majors in `public/data.json`. No backend required.

## Data contract

The app reads a JSON array of majors. Full types in [`src/types.ts`](src/types.ts):

```jsonc
[{
  "cip": "11.0701",              // CIP code
  "major": "Computer science",
  "family": "STEM",              // STEM | Business | Health | Social sci | Humanities | Arts | Trades
  "completions": 200000,         // annual graduates → tile area
  "exposure": 9.0,               // AI exposure 0–10 → color
  "median_pay": 99000,           // USD
  "growth": "faster",            // declining | slower | average | faster
  "occupations": [
    { "soc": "15-1252", "title": "Software developers", "exposure": 9 }
  ],
  "rationale": "Core tasks like coding and analysis are where AI advances fastest."
}]
```

Rows that don't validate are dropped with a console warning; the app renders
whatever remains.

## Environment variables

| Var | Purpose | When unset |
|---|---|---|
| `VITE_DATA_URL` | URL of the majors JSON | uses the bundled `/data.json` |
| `VITE_AGENT_URL` | POST endpoint for the advisor chat | mock echo handler, labeled **Offline preview** in the UI |

Set them in a `.env.local`:

```bash
VITE_DATA_URL=https://your-pipeline.example.com/majors.json
VITE_AGENT_URL=https://your-agent.example.com/chat
```

### Swapping in real data

Point `VITE_DATA_URL` at any endpoint returning the contract above (CORS
permitting), or simply replace `public/data.json`. Tile areas, color domains,
the pay legend, and the heatmap sort all derive from the data at runtime —
nothing else to change.

### Swapping in a real advisor

The chat POSTs `{ "major": string, "cip": string, "message": string }` to
`VITE_AGENT_URL` and accepts either a JSON body with a `reply` (or `message`)
string field, or a plain-text response. Transport lives in
[`src/lib/advisor.ts`](src/lib/advisor.ts). While unset, the panel uses an echo
handler and shows an amber **Offline preview** badge so mock mode is never
mistaken for real advice.

## Project docs

- [`CLAUDE.md`](CLAUDE.md) — project conventions, design system tokens, hard rules.
- [`SKILL.md`](SKILL.md) — step-by-step recipe for the treemap + heatmap visualization.

## Stack

Vite · React 19 · TypeScript (strict) · d3-hierarchy (layout math only — all
SVG is hand-rolled JSX) · Framer Motion · Tailwind CSS 4 (tokens-only theme).

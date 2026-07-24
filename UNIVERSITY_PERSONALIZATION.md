# University personalization — spec + build prompt

## Concept
User enters their university + intended major. The advisor researches that school's program on
the web, compares it to our national AI-exposure/pay data, and advises how to succeed there.
Real sources, cited — never faked school-specific numbers.

## What to add

### 1. `public/universities.json` — the local directory (kills lookup latency)
A static list of US universities, shipped with the app. Source: IPEDS HD directory (`hd2023.csv`
— `UNITID`, `INSTNM`, `STABBR`, `WEBADDR`). Shape:
```json
[{ "unitid": 240444, "name": "University of Washington-Seattle Campus",
   "state": "WA", "domain": "washington.edu" }]
```
Why it matters:
- **Autocomplete is instant** — filtered client-side, zero network per keystroke.
- **`domain` targets the agent's search** — it queries `site:washington.edu <major>` instead of
  guessing, so results are faster and actually about that school.
- **`unitid`** is the join key if we later filter the treemap to that school's IPEDS programs.

### 2. UI — reuse everything, change nothing visual
The university picker is the **same combobox pattern as "Find your major"** (same input, same
glass, same tokens). The compare result renders in the **existing advisor panel** — no new
surface. Keep the popup/CTA the team wants; just make it open this picker.

### 3. Request fields (optional, additive)
Add `university`, `university_domain`, `intended_major` to the advisor request. All optional.
When present, the agent runs the compare mode.

### 4. Agent — reuse the existing advisor + its `google_search`
No new agent. Add one instruction branch: given a school + major, search `site:<domain>` for the
program, summarize what it emphasizes, contrast with our national exposure/pay for that major,
and give concrete "how to succeed" guidance — with cited links.

## Latency plan
1. **Local university lookup** — no web call to find/validate the school. Instant.
2. **Targeted search** via `site:<domain>` — fewer, better search calls than an open query.
3. **Cache by (unitid, major)** with a TTL — repeat asks are instant (same pattern as news).
4. **Real thinking state** during the one web step — no fake progress bars.
5. Everything else stays on-demand; nothing pre-fetched.

## Guardrails (non-negotiable)
- Every school-specific claim cites a real page. If the program isn't found, say so — never
  invent courses, rankings, or outcomes.
- National vs school-specific stays explicit: our exposure/pay are national estimates, not that
  school's numbers.
- Optional and non-blocking; never gate the map or advisor.
- No fabricated data, no fake loading steps.

---

## Prompt for Claude Code

Add "compare my university" to the advisor. Reuse the existing agent and its web search — never
fake school-specific numbers.

Ship a static `public/universities.json` of US universities (fields: unitid, name, state,
domain), sourced from the IPEDS HD directory. The university picker filters this file
client-side so lookup is instant with zero network calls — build it with the SAME combobox/glass
UI as the existing "Find your major" search; nothing visual should change. Keep the existing
popup/CTA; make it open this picker.

Add optional `university`, `university_domain`, and `intended_major` fields to the advisor
request. When present, the agent runs a compare mode: search the web scoped to the school's
domain (`site:<domain> <major> program`) for what that program emphasizes, then contrast it with
our national exposure/pay data for that major and give concrete "how to succeed" guidance.

Latency: the university list must be local (no web call to validate a school); scope the search
to the domain so it's targeted; cache results by (unitid, major) with a TTL so repeat asks are
instant; show the normal thinking state during the web step — no fake progress.

Hard rules: every school-specific claim cites a real page the search returned; if the program
isn't found, say so plainly and never invent courses/rankings/outcomes; keep national-vs-school
explicit (our numbers are national estimates, not the school's). Reuse the existing advisor
agent and its google_search tool — no new agent, just optional fields and one instruction
branch. New schema fields are optional and must not weaken validation on the existing grounded
path.

Guardrails: optional and non-blocking; stay in the glass/token system in UI_REDESIGN.md; keep
pytest green and the typecheck clean.

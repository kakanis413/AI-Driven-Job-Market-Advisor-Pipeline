# Claude Code prompt — university personalization

Add an optional "personalize for my university" mode to the advisor. It takes a school + intended major, runs ONE targeted, cited web search scoped to the school's domain, and layers school-specific "how to succeed" guidance on top of our national exposure/pay/growth data. Never fabricate school-specific numbers. This is fully additive — the national grounded path and all existing tests must keep passing unchanged.

Ground the work in the real code that exists today (do not follow older assumptions in `UNIVERSITY_PERSONALIZATION.md` blindly — the runtime is the `advisor/` package):
- Request/response contract: `advisor/schemas.py` (`AdvisorRequest`, `grounding_block()`).
- Agents: `advisor/agents.py` (`root_agent`, `news_agent` / `news_researcher`, `data_agent`, `ResilientAgentTool`).
- Runtime + TTL cache: `advisor/runtime.py` (`AdvisorRuntime.advise`, `RESPONSE_CACHE`, `_normalize_text`).
- Frontend transport: `src/lib/advisor.ts` (`AdvisorPayload`, request body).
- Chat UI: `src/components/AdvisorPanel.tsx`; combobox to clone: `src/components/SearchSpotlight.tsx`; data-fetch hook pattern: `src/hooks/useMajors.ts`.
- Design authority: `CLAUDE.md` (paper & ink tokens, violet ramp, glass only on floating surfaces, WCAG AA, reduced-motion). Do not introduce raw hex or default Tailwind colors.

## 1. Static data — `public/universities.json`

Ship a static US university directory, served by Vite from `public/`. Shape:
```json
[{ "unitid": 240444, "name": "University of Washington-Seattle Campus", "state": "WA", "domain": "washington.edu" }]
```
- Source it from the IPEDS HD directory (`hd2023.csv`: `UNITID`, `INSTNM`, `STABBR`, `WEBADDR` → derive a bare registrable `domain` from `WEBADDR`). Add a small generator `scripts/build_universities.py` that reads the CSV and writes the JSON, and note the source at the top of the file. Keep only 4-year+ degree-granting institutions to keep the file lean.
- The list is filtered client-side; there is no network call to validate a school.

## 2. Frontend — picker + wiring (reuse, don't reinvent)

- Add `src/hooks/useUniversities.ts` mirroring `useMajors.ts`: fetch `/universities.json` once, cache in memory, expose `{ universities, status }`.
- Add `src/components/UniversityPicker.tsx` that reuses the SAME combobox pattern as `SearchSpotlight` — same glass, same tokens, same keyboard nav (↑/↓/Enter/Esc), same ARIA `combobox`/`listbox`/`option` wiring, same compact pill styling. Filter `name` client-side, cap results (~8). On pick, emit `{ unitid, name, domain }`. Nothing visual should feel new.
- Surface it inside `AdvisorPanel` as an optional, non-blocking affordance: a quiet "Personalize for my school" row above the input that expands to the picker + an intended-major field (defaulting to the currently selected major's name). Once set, show a dismissible chip like `UW · Computer Science`; clearing it returns to the plain national advisor. Never gate the chat or the map behind it.
- Extend `src/lib/advisor.ts`: add optional `university`, `universityDomain`, `intendedMajor` to `AdvisorPayload`, and include `university`, `university_domain`, `intended_major` in the POST body ONLY when present. Keep the existing body untouched when they're absent (backward compatible).

## 3. Backend — schema (additive, don't weaken validation)

In `advisor/schemas.py`, add three optional fields to `AdvisorRequest` (keep `model_config = ConfigDict(extra="ignore")`):
```python
university: str | None = Field(default=None, max_length=200)
university_domain: str | None = Field(default=None, max_length=120)
intended_major: str | None = Field(default=None, max_length=200)
```
- Add a property `is_university_compare` → true when `university` and `university_domain` are both present.
- Extend `grounding_block()`: when `is_university_compare`, append a clearly-labeled `UNIVERSITY CONTEXT` block (school name, domain, intended major) AND an explicit reminder that our exposure/pay/growth are NATIONAL estimates, not this school's numbers. Do not alter the existing verified-data block for the national path.
- Do not tighten or reorder existing validators; existing requests must validate exactly as before.

## 4. Backend — one instruction branch, no new agent

Reuse the existing agents. In `advisor/agents.py`:
- Add ONE branch to `root_agent`'s instruction: when a `UNIVERSITY CONTEXT` block is present, call `news_researcher` with a domain-scoped program query (e.g. `site:<domain> <intended_major> program curriculum OR specializations OR outcomes`). Then root_agent (not the sub-agent) contrasts what that program emphasizes against the national verified data and writes concrete "how to succeed at <school>" guidance. Keep the mandatory exposure-≠-job-loss framing.
- Add ONE clause to `news_agent`'s instruction so it handles a `site:` program lookup correctly: when the query is a university program search, report what the program emphasizes (curriculum, specializations, labs, notable outcomes) with cited page URLs, and note that the recent-30-90-day window does NOT apply to this query type. Keep `google_search` isolated in `news_agent` (ADK requires built-in tools stand alone) and keep it wrapped in `ResilientAgentTool`.
- If the search returns nothing or `status: unavailable`: say plainly that the program page wasn't found, answer from national data only, and never invent courses, rankings, faculty, or outcomes.

## 5. Backend — caching

In `advisor/runtime.py`, fold the school into the cache key so `(university + intended_major + question)` repeats are instant. Extend the `cache_key` built in `advise()` (currently `f"{norm_major}:{norm_query}"`) to include normalized `university` and `intended_major` when present, reusing `_normalize_text`. National requests (no school) must produce the exact same key as today so their cache behavior is unchanged.

## Hard rules / guardrails

- Every school-specific claim cites a real page the search returned. Program not found → say so; never fabricate school numbers, courses, rankings, or outcomes.
- National-vs-school stays explicit in the answer: our numbers are national estimates.
- The feature is optional and non-blocking. With no school set, request, prompt, cache key, and UI are byte-for-byte the current behavior.
- Latency: local university list (no validate call), one domain-scoped search, TTL cache by key, the existing `ThinkingIndicator` for the web step — no fake progress bars.
- Stay in the `CLAUDE.md` glass/token system; no raw hex, no default Tailwind palette, keep keyboard path + reduced-motion + WCAG AA.

## Acceptance checks

- With no university: `/api/v1/analyze-major` behaves identically to today (same grounding block, same cache key); `pytest tests/ -q` stays green and `tsc` / `npm run build` is clean.
- With a university + intended major: the response contains school-specific guidance with at least one cited URL when the program is found, and an explicit "national estimate" note; when the program isn't found, it degrades to national guidance and says so.
- The picker looks and behaves like "find your major" (glass, tokens, keyboard, ARIA); setting/clearing a school never blocks the map or chat.
- Add tests: schema accepts the three optional fields and still rejects the same invalid inputs as before; a mocked compare-mode request routes through `news_researcher` and a not-found search yields a national-only answer.

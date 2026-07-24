# Claude Code prompt — university gate modal + dedicated /chat page

Builds on `UNIVERSITY_PERSONALIZATION_BUILD_PROMPT.md`. The BACKEND from that prompt is unchanged (optional `university` / `university_domain` / `intended_major` on `AdvisorRequest`, one compare-mode branch in `root_agent`, the `site:<domain>` search via the reused `news_researcher`, cache key folds in the school). This prompt REPLACES that prompt's frontend section (§2): instead of an inline picker inside the advisor panel, ship an upsell gate modal plus a new full-page `/chat` route.

Product decisions (fixed):
- The national advisor works fully with NO university — everywhere. A school only ADDS a personalized, cited layer.
- The gate popup appears after the user's FIRST advisor question (first successful send), not before.
- The gate is SOFT — dismissible; dismissal is remembered so it never nags.
- The `/chat` page COEXISTS with the floating advisor panel on Explore (quick panel stays; `/chat` is the roomy home).

Respect `CLAUDE.md`: paper & ink tokens, glass only on floating surfaces (the modal qualifies; the chat body does not), WCAG AA, visible focus rings, full keyboard path, `prefers-reduced-motion` collapses layout animation to a ≤150ms opacity fade, the pinned footer caveat stays visible. No raw hex, no default Tailwind palette.

## 1. Shared university context (survives navigation)

Add `src/hooks/useUniversity.ts`: a small store (module state + `localStorage`, mirroring `useTheme.ts`) holding
```ts
interface UniversityContext { unitid: number; name: string; domain: string; intendedMajor: string } | null
```
plus `gateDismissed: boolean` and `hasChatted: boolean` flags (all persisted). Expose `university`, `setUniversity`, `clearUniversity`, `gateDismissed`, `dismissGate`, `markChatted`. Both the Explore panel and the `/chat` page read this one source, so the school is set once and used everywhere.

## 2. Routing — add the `chat` page

In `src/hooks/useRoute.ts`: add `'chat'` to `Page`; parse `#/chat` (optional `sub` = a CIP to pre-select, e.g. `#/chat/11.0701`). In `src/App.tsx`: render a new `Chat` page for `page === 'chat'`; the global glass header (Logo + NavCluster) should render on `chat` just like it does on `news` (the condition is currently `page !== 'explore'`). In `src/components/Chrome.tsx` `NavCluster`, add `chat` to the nav list (`['explore', 'chat', 'news']`) with the same quiet underline-active styling. Keep the AnimatePresence page transition consistent with the others.

## 3. Gate modal — `src/components/UniversityGateModal.tsx`

A floating glass dialog (this is a legitimate glass surface). Trigger: in `AdvisorPanel`, after the first successful advisor reply, if `!university && !gateDismissed`, open the modal (call `markChatted` so it's once-per-user, not per-message). Content:
- Eyebrow "Get full access"; title like "Add your university for advice built around your school"; one line of body: personalized, cited guidance on top of the national data, and that the advisor keeps working without it.
- A `UniversityPicker` (clone of the `SearchSpotlight` combobox — same glass, tokens, keyboard nav, ARIA `combobox`/`listbox`/`option`; fetches `/universities.json` once via a `useUniversities` hook like `useMajors`; filters `name` client-side, caps ~8).
- An intended-major field defaulting to the currently selected major's name (editable).
- Primary CTA "Personalize my advice →": on submit, `setUniversity({ unitid, name, domain, intendedMajor })` then `nav('chat', selectedCip)`. Secondary ghost "Maybe later": `dismissGate()` and close — national advisor continues in place.
- A11y: `role="dialog"`, `aria-modal`, focus trap, Esc closes (= dismiss), focus returns to the advisor input. Backdrop click dismisses. Reduced-motion: fade only.

## 4. `/chat` page — `src/pages/Chat.tsx`

Full-screen advisor home, reusing existing pieces; coexists with the Explore floating panel (do not remove that).
- Header band shows a removable school chip (violet accent, `#efe9f3` fill / `#432c63` ink — an existing ramp stop, so no new token) like `UW-Seattle · Computer science ✕`; the ✕ calls `clearUniversity()`. If no school is set, show a quiet "Add your university" button that opens the same `UniversityGateModal`.
- Layout: two columns on desktop (`grid-cols-[270px_1fr]`), single column stacked on mobile. Left = a context rail reusing `MajorDetailCard` (or its stat strip) for the selected major, labeled "national estimates", plus a short national-vs-school note. Right = the advisor chat: reuse `AdvisorPanel` at full height (it already renders markdown + clickable citation links).
- If arriving with a CIP sub-route, pre-select that major from `useMajors`; otherwise the chat runs in general/national mode. The advisor must stay fully usable with no school set.
- The chat body is NOT glass (it encodes/holds content); only the header may float. Keep the pinned footer caveat.

## 5. Transport — `src/lib/advisor.ts`

Extend `AdvisorPayload` with optional `university`, `universityDomain`, `intendedMajor`; include `university`, `university_domain`, `intended_major` in the POST body ONLY when a school is set. This applies to BOTH surfaces (the Explore floating panel and `/chat`) — whenever `useUniversity` has a value, every advisor request carries it, so personalization follows the user. With no school, the body is byte-for-byte today's request.

## Acceptance checks

- With no university anywhere: Explore panel and `/chat` behave exactly like today's national advisor; request body, cache key, and the three existing pages are unchanged; `pytest tests/ -q` green and `tsc` / `npm run build` clean.
- Gate: appears only after the first advisor reply, only when no school is set and not previously dismissed; "Maybe later" never shows it again; "Personalize" sets the school and lands on `/chat` with the major pre-selected.
- `/chat`: reachable via nav and `#/chat`; shows the removable school chip; removing it drops back to national mode without breaking the chat; coexists with the still-present Explore panel.
- Personalized answers include at least one cited URL when the program is found and an explicit "national estimate" note; not-found degrades to national and says so.
- Tokens/glass/a11y/reduced-motion all pass; footer caveat stays pinned.

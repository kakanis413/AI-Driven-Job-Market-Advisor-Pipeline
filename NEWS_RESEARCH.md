# News tab — research plan

**Purpose:** validate (or kill) the assumptions in `NEWS_TAB.md` before we build the whole
thing. Scoped for a sprint: ~3 days, 6 participants, not a 4-week study.

---

## 1. What we're assuming — and what happens if we're wrong

`NEWS_TAB.md` rests on five unvalidated beliefs. Each one, if false, changes the build.

| # | Assumption | If it's wrong |
|---|---|---|
| A1 | Students **want news** while exploring majors | We cut the tab entirely and keep news only in chat — saves a whole feature |
| A2 | **Family-level** is the right altitude ("AI news for STEM") | We flip §6 to lazy per-major caching; the family tab becomes secondary or dies |
| A3 | The **chat → tab handoff** drives discovery | The tab needs a real nav entry, not just a CTA from chat |
| A4 | Students **trust AI-summarized** news | We lead with verbatim headlines + source, and cut or shrink summaries |
| A5 | Precomputed (6–24 h old) reads as **"current enough"** | We tighten the TTL, or hide relative time |

**A1 is the one that matters most.** Everything else is a design tweak; A1 decides whether the
feature exists. We're building it because the *spec* asks for a news pillar — not because a
student asked for it. Worth knowing before we spend the days.

---

## 2. Research questions

1. When a student is deciding on / worried about a major, what do they actually go looking for?
   Does news show up unprompted?
2. If news is useful, at what altitude — their exact major, or their broad field?
3. Do they discover the news tab from the chat hand-off? Do they understand what it is?
4. Do they trust an AI-written summary of a news item? Do they click through to the source?
5. What does "recent" mean to them here — today, this week, this month?

---

## 3. Method

**6 × 20-minute in-person sessions.** Concept + usability hybrid — short enough to run between
classes, long enough to watch behavior rather than collect opinions.

Six is enough: for usability issues 5–6 surfaces the large majority; for the "do they want it"
question it gives direction, not certainty. That's the right trade for a sprint.

**Recruiting (campus is the advantage here):**
- 6 undergrads, mixed families — at least 2 STEM, 2 non-STEM, 2 undecided/considering a switch
- Prioritize **students genuinely uncertain about their major** — they're the real target user;
  a confident senior CS major will politely tell you it's neat and mean nothing by it
- Skip friends who know the project. They'll be nice to you, which is useless.

**Materials:** the fixture-based prototype (`public/news.json`, per `NEWS_TAB.md` §8 step 2).
Research and build run in parallel — you don't need the backend.

---

## 4. Session guide

**Warm-up (3 min)**
- What are you studying? How settled do you feel about it?
- *No leading.* Don't mention AI or news yet.

**Context (5 min)** — get the real behavior before showing anything
- Last time you thought about whether your major was the right call — what did you do?
- Where do you go for information about what your major leads to? *(probe: who do you ask, what do you read?)*
- Have you seen anything about AI affecting the kind of work you want to do? Where?
- *Listening for:* does news/current-events surface **unprompted**? That's the A1 signal.

**Task 1 — discovery (5 min)** — hands on the prototype, no instructions
> "You're exploring Psychology here. Find out what's happening recently with AI in this field."
- **Watch:** do they go to the chat, the tab, or neither? Do they find it at all?
- Don't help. Silence is data.

**Task 2 — the hand-off (4 min)**
> "Ask the advisor about recent news in this field."
- **Watch:** do they read the 3 cards or skip to the prose? Do they click a card? Do they
  notice the "More news for {family} →" link — and do they click it?
- Ask after: *"What did you expect that link to do?"*

**Task 3 — the tab (5 min)**
> "You're on the news tab now. Talk me through what you see."
- Probe: *Is this about your major, or something broader? Is that what you wanted?* (A2)
- Probe: *Would you trust this summary, or would you open the article?* (A4)
- Probe: *This says updated 18 hours ago — does that feel current?* (A5)

**Wrap (3 min)**
- If this disappeared tomorrow, would you miss it? *(the honest A1 question)*
- What would make it actually useful to you?

---

## 5. What to record

For each session, one line per finding: **what they did** (not what they said), plus a quote.

- Did news come up unprompted in Context? Y/N ← A1
- Task 1 path: chat / tab / didn't find it ← A3
- Clicked a news card? Y/N ← A4
- Clicked the "more news" CTA? Y/N ← A3
- Wanted major-specific or field-level? ← A2
- Reaction to freshness ← A5

Behavior beats opinion. Everyone says "yeah that's useful." Few click.

---

## 6. Decision rules (agree these *before* running, so results can't be rationalized)

| Finding | Action |
|---|---|
| News comes up unprompted in ≤1 of 6 Context sections | **Cut the tab.** Keep news in chat only. Tell the team the pillar is satisfied conversationally, and say why. |
| 4+ of 6 want their **specific major**, not the field | Flip §6: lazy per-major caching becomes primary; family view is a fallback |
| ≤2 of 6 click the CTA in Task 2 | The tab needs its own nav entry; the chat hand-off can't be the only door |
| 4+ read only the summary, never open the source | Keep summaries but make source + date prominent; consider verbatim headlines |
| 3+ say the summary feels untrustworthy | Lead with the verbatim headline, shrink or drop the AI summary |
| 3+ call 18 h "old" | Tighten TTL toward 6 h |

---

## 7. Timeline

| Day | Work |
|---|---|
| 1 | Build the fixture prototype (tab + 3 cards in chat, `public/news.json`). Recruit 6. |
| 2 | Run all 6 sessions (they're 20 min — this is one afternoon on campus) |
| 3 | Synthesize, apply decision rules, update `NEWS_TAB.md`, share with the team |

---

## 8. What we are deliberately NOT researching

Scope discipline for a sprint — don't let research become the project:

- Visual design preferences (we have a design system; don't relitigate it)
- Card layout A/B tests
- Anything about the treemap or the advisor itself
- Sample sizes big enough for statistics — 6 gives direction, and direction is enough here

---

## 9. The uncomfortable question worth asking

This feature exists because the project spec lists "real-time data and news tracking" as a
pillar — not because a user asked for it. That's a legitimate reason to build it, but it means
we should be honest in the demo about *why* it's there.

If the research says students don't want it, we have two defensible options: build a minimal
version to satisfy the pillar and say so plainly, or make the case that the pillar is better
served by news **inside the advisor**, where it's personalized and asked-for. Either beats
shipping a tab nobody opens and pretending it was user-driven.

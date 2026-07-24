# Tone & palette — proposal

**Status:** proposal only, nothing implemented. For review.
**Problem:** the product currently reads as a threat assessment. The red ramp says *danger* and
the hero asks the reader how vulnerable they are. Both push people away from a tool meant to
help them.

---

## 1. The principle

**Exposure is a magnitude, not a verdict.**

A 9/10 means *AI can do a lot of the tasks in this work* — it does **not** mean the job
disappears or that the student chose wrong. Every design decision below follows from that one
sentence. Where the current design encodes a judgment, we replace it with an encoding of
quantity.

This isn't just tone. It's accuracy: the ember ramp tells a factual lie about our own data.

---

## 2. Palette

### What's wrong with ember
It runs pale sand → gold → copper → **oxblood**. Red is the universal warning color — smoke
alarms, error states, stop signs. A tile turning red reads as *"this major is in trouble,"*
which is precisely the claim our own caveat says we are not making.

### Recommendation: **Violet depth**

| t | Light | Dark |
|---|---|---|
| 0.00 | `#efe9f3` | `#2b2338` |
| 0.25 | `#d5c8e4` | `#463862` |
| 0.50 | `#b09ccc` | `#69538f` |
| 0.75 | `#8567ab` | `#9078bb` |
| 1.00 | `#432c63` | `#c3b2dd` |

**Why violet:**
1. **No cultural valence.** Violet isn't danger, isn't safety, isn't money. It reads as
   *intensity* — exactly what a magnitude scale should encode.
2. **Distinct from the pay ramp.** Pay is sequential blue. When a user flips the layer toggle,
   the change must be unmistakable — an indigo exposure ramp would look like the same layer.
   Violet ≠ blue at every stop.
3. **Cool and calm**, as requested, without going clinical.
4. **Luminance is monotonic**, so it survives color-vision deficiency without relying on hue —
   same guarantee ember had.

### Alternates
- **Ink depth (slate-indigo)** — most on-brand for "paper & ink," but sits close enough to the
  pay blue that the layer toggle loses legibility. Only pick this if the pay ramp moves.
- **Bronze** — the minimal change: keeps the existing warmth and identity, simply stops before
  oxblood. Choose this if the team feels violet is too big a visual reset.

### Constraints that don't change
- Dark mode gets its **own selected stops**, never a filter or auto-flip.
- Tile ink stays computed via `inkFor()` — verify ≥ 4.5:1 at every new stop.
- Exposure is still **always paired with the number**. Color is never the only signal.

---

## 3. Landing page

### What's wrong
> *An interactive field guide to AI & your degree*
> **How exposed is your major to AI?**

Three problems:
1. **It's an accusatory question.** It asks the reader to discover how vulnerable they are.
   A statement about the world invites curiosity; a question about *you* invites anxiety.
2. **"Exposed" means unprotected.** It's the field's technical term, and fine in the
   methodology — but as the first word a student reads, it lands as a threat.
3. **The caveat is in the footer.** The single most reassuring sentence we have is placed
   where it can't defuse the fear the headline just created.

### Recommendation

> **AI is changing the work behind every major.**
> Explore how the day-to-day tasks in your field are shifting — and what stays valuable.
> *High exposure means the work changes, not that the job goes away.*
> **[ Find your major ]**

**What changed and why:**
- **Statement, not question** — describes the world, doesn't interrogate the reader.
- **"the work behind every major"** — universal. Nobody is singled out; every field is
  changing, which is both true and calming.
- **"changing" not "exposed"** — accurate and non-threatening.
- **The caveat moved into the hero**, set in the body style beneath the subhead. It now does
  its job: reassuring *before* the map loads.
- **"Explore" / "Find your major"** — invites browsing rather than delivering a verdict.

### Alternates
- **Agency-forward:** *"Your major isn't your fate."* → *"See how AI is reshaping the work each
  degree leads to — grounded in federal labor data."* Punchier, leans on reassurance; slightly
  more editorial.
- **Curiosity-forward:** *"What will your degree actually be doing in ten years?"* Warmest and
  least threatening, but vaguer about what the tool does.

---

## 4. Microcopy to follow through

Changing the hero and leaving "exposure risk" everywhere else defeats it.

| Where | From | To |
|---|---|---|
| Legend | `Low exposure → High exposure` | `Less AI overlap → More AI overlap` |
| Tooltip label | `AI exposure 9.0/10` | `AI overlap 9.0/10` *(keep the number)* |
| Detail card gauge | `9.0 / 10 exposure` | `9.0 / 10 — how much of this work AI can already do` |
| Empty/low tiles | — | Avoid "safe." Low overlap ≠ safe; it just means less of the work is digital. |

**On the word "exposure":** keep it in the methodology, the data schema, and
`ADK_PRODUCTION.md` — it's the field's term and it's what makes the work defensible to a
technical reviewer. Swap it for plain language only in the student-facing UI.

---

## 5. What we are NOT changing

- The exposure numbers themselves. This is presentation, not data.
- The pay ramp (sequential blue) — it stays, and is why exposure moves to violet.
- Type scale, spacing, radii, motion, dark-mode strategy. No new tokens beyond the five
  ramp stops per mode.
- The pinned caveat in the app shell. It gets *added* to the hero, not moved out of the footer.

---

## 6. Open questions

- [ ] Violet, ink depth, or bronze? (§2)
- [ ] Which hero option — statement, agency, or curiosity? (§3)
- [ ] Do we adopt "AI overlap" in the UI, or keep "exposure" everywhere for consistency with
      the methodology? (§4)
- [ ] Does the landing page need a one-line "where this data comes from" line to build trust
      before the map loads?

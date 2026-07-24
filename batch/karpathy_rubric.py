"""
batch/karpathy_rubric.py

Single source of truth for the Karpathy-style anchored AI-exposure rubric,
shared by the occupation-level (Layer A) and major-level (Layer B) scorers.

Why this file exists: the whole point of the rebuild (see
EXPOSURE_REBUILD_PLAN.md) is that the old task-averaging pipeline compresses
every major into the 2-7 band and can never reach the real 8-10 band. The fix
is to score the *displayed unit* directly against a heavily anchored rubric —
exactly how karpathy.ai/jobs colours its occupations. Keeping the anchor bands
in one place means the occupation scorer and the major scorer calibrate against
the identical yardstick, so the two layers stay comparable.

The anchor bands below are adapted from Karpathy's published 0-10 rubric. The
framing deliberately measures how much the *mix of tasks* is reshaped, NOT job
loss — this matches the pinned caveat the app enforces everywhere.
"""

# The anchored 0-10 ladder. Concrete exemplars at each rung are what force the
# full spread to survive — an LLM given "software developer = 8-9, roofer = 0-1"
# cannot quietly regress everything to the middle the way a triple-average does.
ANCHOR_BANDS = """AI-EXPOSURE SCALE (0-10) — how much AI is likely to reshape the MIX OF TASKS.
A high score means the day-to-day tasks change a lot, NOT that the job or field
disappears. Anchor every score to these bands and their exemplars:

  0-1  Hands-on physical work in the world; almost nothing done at a screen.
       (roofers, divers, loggers, dancers, masons, plumbers on-site)
  2-3  Mostly physical/embodied, with a little digital record-keeping.
       (electricians, carpenters, chefs, welders, agricultural workers)
  4-5  A real mix of hands-on and knowledge work, or heavy in-person human
       contact. (registered nurses, police officers, dental hygienists,
       physical therapists, elementary teachers, social workers)
  6-7  Knowledge work with a meaningful human, physical, or high-stakes
       judgement component. (accountants, lawyers, financial analysts,
       high-school teachers, civil engineers, physicians, HR managers)
  8-9  Fundamentally digital knowledge work done almost entirely at a computer,
       producing text, code, images, analysis, or designs.
       (software developers, data scientists, graphic designers, writers,
       paralegals, market researchers, translators, accountants' modelling)
  10   Routine, structured digital work that current AI can already do almost
       end-to-end. (data-entry keyers, telemarketers, basic bookkeeping clerks)

STRONG PRIOR: fundamentally digital work belongs at 7 or above and is on a
steep AI trajectory — do not under-rate it. Physical, embodied, in-person, and
manual-dexterity work stays low even when it is skilled. Judge the trajectory of
current-generation AI, not only what is shipping this quarter."""

# One line reused in every rationale-writing instruction so the caveat framing
# is present in every stored rationale (a hard app rule).
NO_JOB_LOSS_CLAUSE = (
    "A high score means the tasks are likely to change, NOT that the job "
    "disappears or the field is a bad choice. Never imply job loss."
)

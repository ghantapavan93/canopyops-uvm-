# Two-minute demo script

Prereq: stack running, seeded. Open `http://localhost:4200`. Navigate via the
in-app menu (not the URL bar) so simulated-offline state persists.

**0:00 — The hook (Landing).**
"A closed work order proves an activity was recorded. It doesn’t prove the
*outcome*." Scroll the landing: the gap, the 7-step loop, the four field roles.

**0:20 — Command Center.**
"Exceptions first." Point out the prioritized queue (hazard/overdue at top), the
assurance summary (incomplete evidence, constraint intersects), and the map ⇄ queue
selection. Filters live in the URL — a shareable review link.

**0:40 — Field Execution (offline).**
Switch role to **Field crew**. Toggle connectivity **Off**. Pick a work order, set
coverage to ~60% (partial), arm a **simulated upload failure**, and **Record
execution**. "No signal, no data loss — it’s in the local outbox."

**1:00 — Sync & Conflict Center.**
Click **Simulate concurrent edit** (a manager edited the plan). Toggle **On**. Watch
it **conflict** — your revision 1 vs server revision 2 — then **Adopt server
revision & re-apply**. "Never last-write-wins." Retry the failed upload → evidence
goes to **100% complete**. "A failed upload can’t fake ‘done.’"

**1:25 — Outcome Verification.**
Switch role to **Reviewer**. Open the awaiting-verification record. Note verification
is **blocked** if evidence is incomplete. Choose **Partially effective**, then draw
the **targeted follow-up** — "only the area needing another pass, not a blind
full-corridor repeat." Plan follow-up → **Close**.

**1:45 — Proof Pack + Engineering Evidence.**
The closed record assembles a **Proof Pack**: outcome, geometry, and the full audit
trail (`verified → followup_planned → closed`). Finish on **Engineering Evidence**:
8 backend + 9 frontend tests passing, measured spatial perf, accessibility, and the
honest known-limitations.

**Close.** "Plan to verified outcome, offline-safe, conflict-aware, and defensible
line by line."

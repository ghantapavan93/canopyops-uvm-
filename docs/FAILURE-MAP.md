# Failure map

The edge cases a distributed UVM system must survive, and CanopyOps' **safe
behavior** for each. ✅ = implemented + tested; 🟡 = designed / partially handled;
📋 = recognized, documented safe-behavior, not yet built.

| # | Scenario | Safe behavior | State |
|---|---|---|---|
| 1 | Connectivity lost mid photo-upload | Evidence stays `pending`; the presigned upload can be retried; finalize marks `failed` if the object never landed (recoverable) | ✅ `test_evidence` |
| 2 | App closes before IndexedDB write finishes | The mutation is only enqueued once the IndexedDB transaction commits; an incomplete write is never treated as queued | 🟡 outbox commit boundary |
| 3 | Same submission retried N times | `Idempotency-Key` dedup — one record, replays return the original | ✅ `test_api` |
| 4 | Manager revises the plan while crew offline | Stale `plan_revision` → `409 CONFLICT` with local-vs-server revisions; never last-write-wins | ✅ `test_api` |
| 5 | Same record edited from two devices | Optimistic concurrency: whichever commits second gets the `409` | ✅ (same revision guard) |
| 6 | Device clock is wrong | Server stamps authoritative `performed_at`/timestamps; client time is advisory only | ✅ server-stamped |
| 7 | GPS missing / poor accuracy | Geolocation is optional metadata; a record is never blocked on GPS, and low accuracy is not silently trusted | 🟡 optional field |
| 8 | Self-intersecting / wrong-CRS polygon | `ST_IsValid` + geometry-type/SRID checks reject it (422) before it enters a plan; invalid import features are skipped | ✅ `geo/analyze`, importers |
| 9 | Plan overlaps multiple protected zones | `ST_Intersects` returns all; the strictest (blocking) wins; all are surfaced | ✅ `constraint_flags_for` |
| 10 | Protected-area layer changes after assignment | Zones are a **versioned** snapshot (ETag); a device re-syncs when the version changes | ✅ `geo/zones` (304) |
| 11 | Work order cancelled while offline completion pending | On sync the plan state is re-checked; a completion against a closed/cancelled plan is rejected, not applied | 🟡 status re-check on submit |
| 12 | Browser storage full | The outbox surfaces a storage error rather than silently dropping the mutation | 📋 documented |
| 13 | Very large GeoJSON freezes the UI | Import runs as a **background job** off the request path (worker), not in the browser | ✅ `test_jobs` (geojson_import) |
| 14 | Evidence metadata saved but file storage fails | The record stays incomplete; finalize's object `HEAD` catches the missing file and marks `failed` | ✅ `test_evidence` |
| 15 | User loses permission while app open | RBAC is enforced **server-side** on every mutation; a now-unauthorized call gets `403` regardless of UI state | ✅ `test_risk`, `test_audit` |
| 16 | Import contains duplicate identifiers | Corridor import is additive and reports imported/skipped; unique constraints reject true key collisions | 🟡 skip + report |
| 17 | Proof Pack job fails after verification succeeds | Verification is committed independently; the Proof Pack is a **retryable job** (backoff → terminal `failed`) that never rolls back the verified outcome | ✅ `test_jobs` (retry) |
| 18 | Downstream client integration unavailable | Integration is read-model/adapter-shaped; an unavailable consumer never blocks the core workflow | 🟡 adapter seam |
| 19 | Map layer stale vs. current business records | Business state (DB) is authoritative; map context layers are versioned/cacheable and labelled as reference | 🟡 versioned zones |
| 20 | Records cross DST / time-zone boundaries | All timestamps are stored **timezone-aware (UTC)**; formatting is presentation-only | ✅ `DateTime(timezone=True)` |

See [`RUNBOOK.md`](./RUNBOOK.md) for operational recovery (RPO/RTO, backups) and
[`ARCHITECTURE.md`](./ARCHITECTURE.md) for the state machine these guard.

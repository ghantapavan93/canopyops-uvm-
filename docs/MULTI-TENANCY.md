# Multi-tenancy (per-program isolation)

A UVM contractor serves many utility clients (programs). CanopyOps isolates each
program's data so one program can never see or touch another's — enforced at the
data-access layer, not just hidden in the UI.

## Model

- A **`tenant`** is a program / utility client. Its `id` is a stable slug
  (`demo`, `northgrid`) so it can ride in the JWT with no extra DB lookup.
- Every program-owned table carries a `tenant_id` (FK → `tenant`): corridors,
  work orders, treatment plans, executions, evidence, verifications, sync
  attempts, risk reviews, quality audits, jobs, audit events.
- `app_user` carries a `tenant_id` (membership) but is **not** auto-scoped —
  login must find a user before the tenant is known.
- `environmental_constraint` (protected zones) is **shared reference data**, not
  tenant-scoped.

## Enforcement (active, tested)

The current tenant lives in a `ContextVar`, set per request from the JWT's
`tenant` claim by `tenant_scope_middleware` (unauthenticated/public requests
resolve to the default `demo` program). Two SQLAlchemy `Session` hooks
(`app/core/tenancy.py`) then enforce isolation **automatically**:

1. **Read filter** — a `do_orm_execute` listener adds
   `with_loader_criteria(TenantScoped, tenant_id == current)` to **every** ORM
   `SELECT`. A forgotten `WHERE tenant_id` can't leak data — the filter is applied
   centrally, not per query.
2. **Write stamp** — a `before_flush` listener stamps the current tenant onto any
   new tenant-scoped row, so inserts are automatically attributed.

The few **raw-SQL** spatial queries (HFTD intersection, constraint intersection)
bypass the ORM, so they add an explicit `AND p.tenant_id = :tid`. The background
**worker** spans all programs when claiming jobs, but sets the ContextVar to the
job's own tenant before running the handler, so a Proof Pack is assembled only
from its program's data.

Proven in `tests/test_tenancy.py`: a NorthGrid user sees only NorthGrid
corridors; a demo user fetching a NorthGrid plan id gets `404` (it doesn't exist
for them, not `403`); the two programs' plan lists are disjoint; and a row created
under one program is invisible to the other. Try it live: the header's program
switcher (**NorthGrid ⧉**) logs in as a different program and the whole console's
data changes.

## Defense-in-depth: database Row-Level Security (RLS) — **enabled**

The app-layer filter is one guarantee; the **database enforces a second**, so a
raw query or an ORM-filter bug still can't cross programs. This is live in the
demo (migration `f7a1c2d8e934`):

- **A non-superuser app role.** The API + worker connect as `canopyops_app`
  (superusers bypass RLS); migrations and seeding use the superuser via
  `ADMIN_DATABASE_URL`.
- **A transaction GUC.** A SQLAlchemy `after_begin` hook runs
  `SELECT set_config('app.tenant_id', :tenant, true)` at the start of every
  transaction from the request/worker's ContextVar. Being **transaction-local**,
  it clears on commit — a pooled connection never carries a stale program.
- **Policies** on every program-owned table (`job` excluded — the worker claims
  across programs, then runs each job under its own program):

```sql
ALTER TABLE treatment_plan ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON treatment_plan
  USING      (tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
```

Proven at the DB (see `test_rls_enforced_at_the_database_even_for_raw_sql` and a
psql check): as `canopyops_app`, a **raw** `SELECT count(*) FROM treatment_plan`
returns 6 with `app.tenant_id=demo`, 1 with `northgrid`, and **0 with the GUC
unset** (fail-closed) — while the superuser sees all 7 (RLS bypassed).

An unset GUC yielding zero rows is deliberate: every HTTP request sets a program
(the default `demo` for public/unauthenticated), and only trusted infra
(migrations/seed as superuser; the worker's cross-program job claim on the
RLS-exempt `job` table) runs without it.

## Known limitations

- Cross-program **admin** views (a contractor seeing all programs at once) would
  use an explicit unscoped context (`skip_tenant_filter`), not built here.
- Per-program quotas/rate-limits and per-program object-storage prefixes are
  natural follow-ups.

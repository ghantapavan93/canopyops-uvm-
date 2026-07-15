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

## Production hardening: database Row-Level Security (RLS)

The app-layer filter above is the active guarantee. For defense-in-depth, add
Postgres **RLS** so the *database* refuses cross-tenant rows even for a raw query
or a bug. It requires (a) a **non-superuser** app role (superusers bypass RLS),
and (b) setting the tenant as a transaction GUC in `get_db`
(`SET LOCAL app.tenant_id = :tenant`). Then, per scoped table:

```sql
ALTER TABLE treatment_plan ENABLE ROW LEVEL SECURITY;
ALTER TABLE treatment_plan FORCE  ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON treatment_plan
  USING      (tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT, INSERT, UPDATE, DELETE ON treatment_plan TO canopyops_app;
```

This is documented rather than enabled in the demo because the compose Postgres
role is a superuser (which bypasses RLS) and the GUC must be transaction-scoped;
wiring both is the production step. The app-layer enforcement is what the tests
exercise today.

## Known limitations

- Cross-program **admin** views (a contractor seeing all programs at once) would
  use an explicit unscoped context (`skip_tenant_filter`), not built here.
- Per-program quotas/rate-limits and per-program object-storage prefixes are
  natural follow-ups.

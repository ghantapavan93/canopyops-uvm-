# Resume & outreach — truthful, evidence-backed

Every claim below is demonstrable in the running app or the test suites. Use only
what remains true if the reviewer opens the code.

## Project entry

**CanopyOps — Treatment Assurance** · *Angular, TypeScript, MapLibre GL, PostGIS,
FastAPI, IndexedDB/PWA, Jest, Cypress, Docker*

Built a responsive UVM treatment-assurance platform that connects GIS-based
planning, offline field execution, evidence completeness, environmental
constraints, and human-approved outcome verification into one auditable workflow.
Implemented reusable Angular standalone components with Signals/RxJS, a MapLibre map
with server-side PostGIS spatial filtering, an IndexedDB offline outbox with
idempotent sync and revision-conflict resolution, JWT + server-enforced RBAC, and
Jest/pytest test suites — verified end-to-end across desktop and mobile.

## Bullet points

- Designed an **offline-first field workflow** (IndexedDB outbox + idempotency keys
  + revision checks) that survives connectivity loss and page refresh with **zero
  duplicate records** on retry, and resolves concurrent-edit conflicts without
  last-write-wins.
- Built an **interactive GIS layer** on MapLibre + PostGIS with planned-vs-actual
  coverage, constraint intersection (`ST_Intersects`), and **server-side bbox
  filtering measured at ~53 ms over 1,006 features**, plus an accessible list
  equivalent for all map information.
- Implemented an **evidence-completeness gate** and role-gated, human-authored
  outcome verification, enforcing a treatment state machine and an immutable audit
  trail server-side (not UI-only).
- Delivered **reusable, accessible Angular components** (WCAG non-color status,
  keyboard navigation, reduced-motion) with Tailwind design tokens, responsive from
  mobile field screens to desktop split-view.
- Established **quality evidence**: 25 backend (pytest) + 12 frontend (Jest) tests and a
  **passing Cypress** critical-journey e2e, Docker-based local env, and GitHub Actions CI.

## 30-second outreach message

> I noticed that vegetation software can record completed field work, but the harder
> operational question comes later: did the intervention create the intended result,
> and can the team prove it? I built an independent Angular + GIS prototype —
> CanopyOps — that connects planned treatment geometry, offline field evidence, sync
> recovery, and follow-up verification into one auditable workflow. It runs from a
> single link, uses only synthetic data, and I can walk through the field-to-verified
> flow — including how it survives lost signal and concurrent edits — in about two
> minutes.

## What I’d change with real Davey users and APIs

Wire the map to tiled production basemaps; integrate real work-order/GIS sources
behind the same typed contracts; add resumable evidence uploads and object storage;
extend the data model’s attach-ready hooks for LiDAR/multispectral; and validate the
verification policies and constraint rules with actual foresters and compliance
staff.

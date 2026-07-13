# Traceability — role requirements → product evidence

Maps the **UVM Front-End Developer** (Req 224542) and **UVM Full-Stack Developer**
(Req 224544) requirements to where they are demonstrated in this project.

## Front-end requirements

| Requirement | Evidence |
|---|---|
| HTML, CSS, JavaScript | Angular 18 + TypeScript throughout; semantic HTML; SCSS design tokens (`src/styles.scss`) |
| Responsive design across devices | Tailwind breakpoints; desktop split-view Command Center; mobile-first Field Execution with large touch targets |
| Clean, documented, testable code | Small modules named by responsibility; pure `core/geometry.ts` unit-tested; commented services |
| Cross-browser / cross-platform | Standard web platform + MapLibre WebGL, no browser-specific APIs; documented Chrome/Edge/Firefox/Safari matrix |
| Testing & QA | Jest component/unit tests (9), Cypress critical-journey spec, Engineering Evidence route |
| Code review, best practices | DRY (shared `status.ts`, `geometry.ts`), typed contracts, ADRs documenting rejected alternatives |
| Collaboration with designers/PMs/backend | Typed REST contract shared by front and back (camelCase DTOs mirror TS models) |
| Integrate user-facing elements with server-side logic | `ApiService` + auth interceptor → FastAPI; optimistic UI only for reversible edits |
| Latest technologies & UX | Signals + RxJS, PWA/IndexedDB offline, CSS-driven scrollytelling landing, WCAG-minded UI |
| Security best practices (auth/authz) | JWT auth, server-enforced RBAC, opaque storage keys, token only attached to `/api` |
| **Angular (preferred)** | Angular 18 standalone components, DI, router, reactive forms, signals |
| **Jest** | `jest` + `jest-preset-angular`, 9 passing tests |
| **Git** | Conventional structure, CI on push/PR |
| **GIS concepts** | MapLibre + PostGIS: planned-vs-actual coverage, constraint intersection (ST_Intersects), targeted follow-up geometry, server-side bbox filtering, accessible list equivalent |

## Full-stack requirements

| Requirement | Evidence |
|---|---|
| Back-end services | FastAPI modular monolith; work order / plan / execution / evidence / verification / sync / audit modules |
| Database | PostgreSQL 16 + PostGIS; SQLAlchemy 2 + GeoAlchemy2; Alembic migration with GIST spatial indexes |
| API design | Typed REST, structured error envelopes, correlation IDs, idempotency keys, revision checks |
| Auth & security | JWT, role-based authorization enforced server-side, synthetic-only data |
| Deployment | Docker Compose (web+api+db), multi-stage frontend image + nginx `/api` proxy, GitHub Actions CI |
| Performance | Server-side spatial filtering (measured ~53 ms over 1,006 features), lazy routes, connection pooling |
| SDLC participation | ADRs, failure map, traceability, test plan, honest known-limitations |

## Accessibility (Passion for great UX)

Non-color status (text + shape + color), keyboard navigation with visible focus,
ARIA roles/labels/live regions, a synchronized list equivalent for all map
information, and `prefers-reduced-motion` honored across all animation.

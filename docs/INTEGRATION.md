# Integration architecture

**Short version:** this is a real, standard, production-shaped architecture — a
typed REST API over PostgreSQL/PostGIS, containerized, JWT-secured, with a live
OpenAPI contract. It runs on **synthetic data by design**, but every code path is
real: the same contracts that power the demo power a real integration. Nothing is
mocked.

This document is the honest map of *how a utility would connect it to their own
systems*, and what is prototype-grade vs. production-ready.

## The integration seam: a typed contract

The whole system talks over one **typed REST contract** with an auto-generated
**OpenAPI 3 spec**:

- **Swagger UI:** `/api/docs` · **ReDoc:** `/api/redoc` · **Spec:** `/api/openapi.json`

Any external system (GIS, EAM, BI, a mobile app) can generate a client from that
spec. Requests carry a JWT bearer token; responses are camelCase JSON with
structured error envelopes and an `X-Correlation-Id` for tracing.

## Test it with your own data — today

The platform is not locked to its seed data. Load your own ROW centerlines and
they render on the map immediately:

```bash
# 1) get a manager token
TOKEN=$(curl -s -X POST http://localhost:8080/api/auth/token \
  -d "username=manager@synthetic.test&password=canopyops" | jq -r .accessToken)

# 2) POST a standard GeoJSON FeatureCollection of LineString corridors
curl -X POST http://localhost:8080/api/import/corridors \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{ "type":"FeatureCollection", "features":[
        { "type":"Feature",
          "properties": { "circuitId":"CKT-1201", "spanLabel":"SPAN 4-5", "name":"River Rd", "voltageKv":138 },
          "geometry": { "type":"LineString", "coordinates": [[-83.05,40.02],[-83.04,40.03]] } } ] }'
# → { "imported": 1, ... }  Now visible at /api/corridors and on the Command Center map.
```

Recognized feature properties: `circuitId`, `spanLabel`, `name`, `voltageKv`
(snake_case accepted). Invalid/non-LineString features are skipped, not fatal.

## How synthetic swaps to real systems

The data layer is a repository/adapter seam — the API depends on typed models,
not on where the data came from. To integrate:

| Concern | Prototype today | Production swap |
|---|---|---|
| **ROW / GIS geometry** | Synthetic GeoJSON + PostGIS; import endpoint | Read from the utility's Esri/ArcGIS or PLS-CADD source into PostGIS; server-side spatial queries unchanged |
| **Work orders** | Created in-app / seeded | Ingest from the EAM (Maximo/SAP/etc.) via the same typed `WorkOrder` contract |
| **Field capture / sync** | IndexedDB outbox → idempotent REST | Same offline protocol; back it with the utility's field platform. Idempotency-Key + revision checks already prevent duplicates/conflicts |
| **Evidence storage** | Opaque `storage_key` abstraction | Point the object-storage adapter at S3/Azure Blob; add resumable upload + AV scan |
| **Auth** | Synthetic JWT + server-enforced RBAC | Swap the token issuer for the utility's **SSO/OIDC**; RBAC roles map to their directory groups. Enforcement code is unchanged |
| **Remote sensing** | Attach-ready data shape | Attach LiDAR/multispectral layers to the existing evidence/geometry model |

Because authorization, spatial logic, idempotency, and the state machine are all
enforced **server-side** (not in the UI), the integration surface is small and the
guarantees hold regardless of the client.

## Deployment

- **One command:** `docker compose up --build` → web (nginx) + api (FastAPI) +
  db (PostGIS). Nginx serves the built SPA and proxies `/api`.
- **12-factor config** via environment (`DATABASE_URL`, `JWT_SECRET`,
  `FRONTEND_ORIGIN`).
- **Migrations:** Alembic (`alembic upgrade head`) on start.
- **CI:** GitHub Actions runs pytest + Jest + build on every push.
- **Scale path:** modular monolith now; module boundaries are drawn so services
  can be split later if load requires it (documented in ADR-1).

## What is prototype-grade (honest boundaries)

- Data is synthetic; auth issues its own tokens (no real IdP wired).
- Object storage is an abstraction, not a real bucket; uploads aren't resumable
  or virus-scanned yet.
- No real GIS/EAM connector ships — the seam and the import path are provided.
- See [`README.md`](../README.md) "Known limitations" for the full list.

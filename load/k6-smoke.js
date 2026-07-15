// k6 load test for the CanopyOps API — the reproducible artifact.
//
//   Run the stack with the load-test overrides (rate limit lifted so we measure
//   server latency, not the limiter), then:
//     k6 run -e BASE=http://localhost:8001/api load/k6-smoke.js
//
// Thresholds encode the documented service targets (docs/SLO.md): non-spatial
// p95 < 500 ms, spatial p95 < 1500 ms, error rate < 1%.
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '20s', target: 50 },
        { duration: '40s', target: 50 },
        { duration: '10s', target: 0 },
      ],
    },
  },
  thresholds: {
    'http_req_duration{endpoint:health}': ['p(95)<500'],
    'http_req_duration{endpoint:overview}': ['p(95)<1500'],
    'http_req_duration{endpoint:risk}': ['p(95)<1500'],
    http_req_failed: ['rate<0.01'],
  },
};

const BASE = __ENV.BASE || 'http://localhost:8001/api';

export default function () {
  http.get(`${BASE}/health`, { tags: { endpoint: 'health' } });
  const o = http.get(`${BASE}/overview`, { tags: { endpoint: 'overview' } });
  check(o, { 'overview 200': (r) => r.status === 200 });
  const r = http.get(`${BASE}/risk/spans`, { tags: { endpoint: 'risk' } });
  check(r, { 'risk 200': (x) => x.status === 200 });
}

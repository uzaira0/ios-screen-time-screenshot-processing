/**
 * k6 load test — smoke test tier.
 *
 * Verifies the API handles concurrent users without errors.
 * Run: k6 run tests/load/smoke.js
 *
 * Tiers:
 *   smoke:  1 VU, 30s  (sanity check)
 *   load:   50 VUs, 5m (normal load)
 *   stress: 200 VUs, 2m (breaking point)
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const errorRate = new Rate("errors");

// Configuration — override with k6 --env flags
const BASE_URL = __ENV.BASE_URL || "http://localhost:8002";
const USERNAME = __ENV.USERNAME || "load-tester";
const SITE_PASSWORD = __ENV.SITE_PASSWORD || "";

const headers = {
  "X-Username": USERNAME,
  "Content-Type": "application/json",
};
if (SITE_PASSWORD) {
  headers["X-Site-Password"] = SITE_PASSWORD;
}

export const options = {
  scenarios: {
    smoke: {
      executor: "constant-vus",
      vus: 1,
      duration: "30s",
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<500"],  // 95% of requests under 500ms
    errors: ["rate<0.01"],             // <1% error rate
  },
};

export default function () {
  // Health check
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    "health status 200": (r) => r.status === 200,
  }) || errorRate.add(1);

  // Stats endpoint
  const statsRes = http.get(`${BASE_URL}/api/v1/screenshots/stats`, { headers });
  check(statsRes, {
    "stats status 200": (r) => r.status === 200,
    "stats has total": (r) => {
      try { return JSON.parse(r.body).total !== undefined; }
      catch { return false; }
    },
  }) || errorRate.add(1);

  // Screenshot list (paginated)
  const listRes = http.get(`${BASE_URL}/api/v1/screenshots/list?page=1&page_size=10`, { headers });
  check(listRes, {
    "list status 200": (r) => r.status === 200,
  }) || errorRate.add(1);

  // Groups
  const groupsRes = http.get(`${BASE_URL}/api/v1/screenshots/groups`, { headers });
  check(groupsRes, {
    "groups status 200": (r) => r.status === 200,
  }) || errorRate.add(1);

  sleep(1);
}

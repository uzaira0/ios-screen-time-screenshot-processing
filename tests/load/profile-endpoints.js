/**
 * k6 per-endpoint load profiling scenario.
 *
 * Sweeps each API endpoint with ramping VUs (1 → 10 → 50 → 100) over 2 minutes
 * to identify which endpoints degrade under load.
 *
 * Run:
 *   k6 run tests/load/profile-endpoints.js
 *   k6 run --out json=profiling-reports/api/k6-results.json tests/load/profile-endpoints.js
 *
 * Override:
 *   k6 run --env BASE_URL=http://localhost:8002 --env SITE_PASSWORD=secret tests/load/profile-endpoints.js
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate, Counter } from "k6/metrics";

// Custom metrics per endpoint
const healthLatency = new Trend("health_latency", true);
const statsLatency = new Trend("stats_latency", true);
const listLatency = new Trend("list_latency", true);
const groupsLatency = new Trend("groups_latency", true);
const nextLatency = new Trend("next_latency", true);
const errorRate = new Rate("errors");
const requestCount = new Counter("total_requests");

// Configuration
const BASE_URL = __ENV.BASE_URL || "http://localhost:8002";
const USERNAME = __ENV.USERNAME || "profile-tester";
const SITE_PASSWORD = __ENV.SITE_PASSWORD || "";

export const options = {
  scenarios: {
    ramp_profile: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "15s", target: 1 },   // Baseline: 1 VU
        { duration: "15s", target: 10 },  // Ramp up
        { duration: "30s", target: 10 },  // Sustain 10
        { duration: "15s", target: 50 },  // Ramp up
        { duration: "30s", target: 50 },  // Sustain 50
        { duration: "15s", target: 100 }, // Peak
        { duration: "30s", target: 100 }, // Sustain peak
        { duration: "10s", target: 0 },   // Ramp down
      ],
    },
  },
  thresholds: {
    health_latency: ["p(95)<200"],   // Health should be fast
    stats_latency: ["p(95)<1000"],   // Stats can be slower
    list_latency: ["p(95)<1000"],    // List with pagination
    groups_latency: ["p(95)<1000"],  // Groups
    errors: ["rate<0.05"],           // <5% error rate
  },
};

// setup() runs once before the test — authenticates and returns shared data
export function setup() {
  // Login via session endpoint to get a cookie
  const loginRes = http.post(
    `${BASE_URL}/api/v1/auth/session/login`,
    JSON.stringify({ username: USERNAME, password: SITE_PASSWORD }),
    { headers: { "Content-Type": "application/json" } }
  );

  const loginOk = check(loginRes, {
    "login 200": (r) => r.status === 200,
  });

  // Extract session cookie
  let sessionCookie = "";
  if (loginOk && loginRes.cookies && loginRes.cookies.session_token) {
    sessionCookie = loginRes.cookies.session_token[0].value;
  }

  // Also build header-based auth as fallback
  const headers = {
    "X-Username": USERNAME,
    "Content-Type": "application/json",
  };
  if (SITE_PASSWORD) {
    headers["X-Site-Password"] = SITE_PASSWORD;
  }

  return { headers, sessionCookie };
}

export default function (data) {
  const params = { headers: data.headers };

  // Add session cookie if we have one
  if (data.sessionCookie) {
    params.headers = Object.assign({}, data.headers);
    // k6 handles cookies via jar, but we also pass header auth as backup
  }

  // 1. Health check (no auth needed)
  const healthRes = http.get(`${BASE_URL}/health`);
  healthLatency.add(healthRes.timings.duration);
  requestCount.add(1);
  check(healthRes, { "health 200": (r) => r.status === 200 }) || errorRate.add(1);

  // 2. Stats endpoint
  const statsRes = http.get(`${BASE_URL}/api/v1/screenshots/stats`, params);
  statsLatency.add(statsRes.timings.duration);
  requestCount.add(1);
  check(statsRes, { "stats 200": (r) => r.status === 200 }) || errorRate.add(1);

  // 3. Screenshot list (paginated)
  const listRes = http.get(
    `${BASE_URL}/api/v1/screenshots/list?page=1&page_size=10`,
    params
  );
  listLatency.add(listRes.timings.duration);
  requestCount.add(1);
  check(listRes, { "list 200": (r) => r.status === 200 }) || errorRate.add(1);

  // 4. Groups
  const groupsRes = http.get(`${BASE_URL}/api/v1/screenshots/groups`, params);
  groupsLatency.add(groupsRes.timings.duration);
  requestCount.add(1);
  check(groupsRes, { "groups 200": (r) => r.status === 200 }) || errorRate.add(1);

  // 5. Next screenshot (may 404 if none pending — not an error)
  const nextRes = http.get(`${BASE_URL}/api/v1/screenshots/next`, params);
  nextLatency.add(nextRes.timings.duration);
  requestCount.add(1);
  check(nextRes, {
    "next 200 or 404": (r) => r.status === 200 || r.status === 404,
  }) || errorRate.add(1);

  sleep(0.5);
}

export function handleSummary(data) {
  const endpoints = [
    { name: "/health", metric: "health_latency" },
    { name: "/screenshots/stats", metric: "stats_latency" },
    { name: "/screenshots/list", metric: "list_latency" },
    { name: "/screenshots/groups", metric: "groups_latency" },
    { name: "/screenshots/next", metric: "next_latency" },
  ];

  let report = "\n=== Endpoint Performance Profile ===\n\n";
  report += `${"Endpoint".padEnd(30)} ${"p50".padStart(8)} ${"p95".padStart(8)} ${"p99".padStart(8)} ${"max".padStart(8)}\n`;
  report += "-".repeat(66) + "\n";

  for (const ep of endpoints) {
    const m = data.metrics[ep.metric];
    if (m && m.values) {
      report += `${ep.name.padEnd(30)} ${(m.values["p(50)"] || 0).toFixed(1).padStart(7)}ms ${(m.values["p(95)"] || 0).toFixed(1).padStart(7)}ms ${(m.values["p(99)"] || 0).toFixed(1).padStart(7)}ms ${(m.values["max"] || 0).toFixed(1).padStart(7)}ms\n`;
    }
  }

  report += "\n";
  report += `Total requests: ${data.metrics.total_requests ? data.metrics.total_requests.values.count : 0}\n`;
  report += `Error rate: ${data.metrics.errors ? (data.metrics.errors.values.rate * 100).toFixed(2) : 0}%\n`;

  console.log(report);

  return {
    stdout: report,
  };
}

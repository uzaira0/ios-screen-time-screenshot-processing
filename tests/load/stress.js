/**
 * k6 stress test — finds breaking points.
 * Run: k6 run tests/load/stress.js
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const errorRate = new Rate("errors");
const BASE_URL = __ENV.BASE_URL || "http://localhost:8002";
const USERNAME = __ENV.USERNAME || "stress-tester";
const SITE_PASSWORD = __ENV.SITE_PASSWORD || "";

const headers = { "X-Username": USERNAME };
if (SITE_PASSWORD) headers["X-Site-Password"] = SITE_PASSWORD;

export const options = {
  stages: [
    { duration: "30s", target: 10 },   // ramp up
    { duration: "1m", target: 50 },    // hold at 50
    { duration: "30s", target: 100 },  // push to 100
    { duration: "30s", target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<2000"],
    errors: ["rate<0.1"],
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/api/v1/screenshots/stats`, { headers });
  check(res, { "status 200": (r) => r.status === 200 }) || errorRate.add(1);

  const listRes = http.get(`${BASE_URL}/api/v1/screenshots/list?page=1&page_size=5`, { headers });
  check(listRes, { "list ok": (r) => r.status === 200 }) || errorRate.add(1);

  sleep(0.5);
}

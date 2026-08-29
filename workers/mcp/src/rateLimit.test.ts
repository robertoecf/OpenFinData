import assert from "node:assert/strict";
import { test } from "node:test";
import {
  MCP_BURST_PERIOD_S,
  MCP_MINUTE_PERIOD_S,
  clientKey,
  enforceMcpRateLimits,
  rateLimitedResponse,
} from "./rateLimit.ts";

function requestWith(headers: Record<string, string>): Request {
  return new Request("https://openfindata.com.br/mcp", { headers });
}

test("clientKey prefers cf-connecting-ip", () => {
  const request = requestWith({
    "cf-connecting-ip": "198.51.100.7",
    "x-forwarded-for": "203.0.113.9",
  });
  assert.equal(clientKey(request), "mcp:198.51.100.7");
});

test("clientKey does not trust x-forwarded-for", () => {
  assert.equal(clientKey(requestWith({ "x-forwarded-for": "203.0.113.9" })), "mcp:unknown");
});

test("429 body and Retry-After are synchronous", async () => {
  const response = rateLimitedResponse(MCP_MINUTE_PERIOD_S);
  assert.equal(response.status, 429);
  assert.equal(response.headers.get("retry-after"), String(MCP_MINUTE_PERIOD_S));
  assert.deepEqual(await response.json(), { error: "rate_limited" });
});

test("minute limit failure returns Retry-After 60", async () => {
  const response = await enforceMcpRateLimits(
    requestWith({ "cf-connecting-ip": "198.51.100.7" }),
    { limit: async () => ({ success: false }) },
    { limit: async () => ({ success: true }) },
  );
  assert.ok(response);
  assert.equal(response.status, 429);
  assert.equal(response.headers.get("retry-after"), String(MCP_MINUTE_PERIOD_S));
});

test("burst limit failure returns Retry-After 10", async () => {
  const response = await enforceMcpRateLimits(
    requestWith({ "cf-connecting-ip": "198.51.100.7" }),
    { limit: async () => ({ success: true }) },
    { limit: async () => ({ success: false }) },
  );
  assert.ok(response);
  assert.equal(response.status, 429);
  assert.equal(response.headers.get("retry-after"), String(MCP_BURST_PERIOD_S));
});

test("both limits succeeding returns null", async () => {
  const response = await enforceMcpRateLimits(
    requestWith({ "cf-connecting-ip": "198.51.100.7" }),
    { limit: async () => ({ success: true }) },
    { limit: async () => ({ success: true }) },
  );
  assert.equal(response, null);
});

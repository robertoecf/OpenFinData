import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { unstable_startWorker } from "wrangler";

let worker: Awaited<ReturnType<typeof unstable_startWorker>>;
before(async () => {
  worker = await unstable_startWorker({
    config: "wrangler.toml",
    dev: { remote: false, persist: false, server: { hostname: "127.0.0.1", port: 0 } },
  });
  await worker.ready;
});
after(async () => { await worker?.dispose(); });

async function post(method: string, params: unknown, protocol = "2025-11-25") {
  return worker.fetch("http://localhost/mcp", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      "MCP-Protocol-Version": protocol,
      "cf-connecting-ip": "198.51.100.10",
    },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    signal: AbortSignal.timeout(15000),
  });
}
async function result(response: Response) {
  assert.equal(response.status, 200);
  const text = await response.text();
  const data = text.split("\n").find((line) => line.startsWith("data: "));
  assert.ok(data, text);
  return JSON.parse(data.slice(6));
}

test("concurrent requests with the same RPC ID retain independent transports", async () => {
  const responses = await Promise.all([post("tools/list", {}), post("tools/list", {})]);
  for (const response of responses) {
    const message = await result(response);
    assert.equal(message.id, 1);
    assert.ok(message.result.tools.some((tool: { name: string }) => tool.name === "bcb_series"));
  }
});

test("both protocol lanes reject oversized bodies without Content-Length", async () => {
  for (const protocol of ["2025-11-25", "2026-07-28"]) {
    const response = await post("tools/list", { padding: "a".repeat(64 * 1024) }, protocol);
    assert.equal(response.status, 413);
    assert.deepEqual(await response.json(), { error: "payload_too_large" });
  }
});

test("tool element budget rejects excess input while the public catalog remains usable", async () => {
  const rejected = await result(await post("tools/call", {
    name: "bcb_series", arguments: { padding: Array(1001).fill(0) },
  }));
  assert.equal(rejected.result.isError, true);
  assert.match(rejected.result.content[0].text, /maximum.*1000.*elements/);
  const accepted = await result(await post("tools/call", { name: "bcb_series", arguments: {} }));
  assert.notEqual(accepted.result.isError, true);
  assert.ok(accepted.result.content.length > 0);
});

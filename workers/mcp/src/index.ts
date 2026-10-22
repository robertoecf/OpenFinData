import { readRequestBody } from "@modelcontextprotocol/server";
import { createMcpHandler } from "agents/mcp/server";
import { enforceMcpRateLimits } from "./rateLimit";
import { createServer } from "./server";

const MAX_REQUEST_BYTES = 64 * 1024;
const mcp = createMcpHandler(createServer, {
  route: "/mcp",
  maxRequestBodySize: MAX_REQUEST_BYTES,
});

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return Response.json({
        status: "ok",
        surface: "mcp-worker",
        version: "0.3.3",
        mcp: "/mcp",
      });
    }
    if (url.pathname === "/mcp" || url.pathname.startsWith("/mcp/")) {
      const limited = await enforceMcpRateLimits(
        request,
        env.MCP_RATE_LIMIT,
        env.MCP_BURST_LIMIT,
      );
      if (limited) {
        return limited;
      }
      // Agents' legacy compatibility path does not forward maxRequestBodySize.
      // Bound the stream before either protocol path parses the JSON payload.
      if (request.method === "POST") {
        const body = await readRequestBody(request, MAX_REQUEST_BYTES);
        if (body.tooLarge) {
          return Response.json({ error: "payload_too_large" }, { status: 413 });
        }
        request = new Request(request, { body: body.text });
      }
      return mcp(request, env, ctx);
    }
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;

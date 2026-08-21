import { createMcpHandler } from "agents/mcp/server";
import { enforceMcpRateLimits } from "./rateLimit";
import { createServer } from "./server";

const mcp = createMcpHandler(createServer, { route: "/mcp" });

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return Response.json({
        status: "ok",
        surface: "mcp-worker",
        version: "0.3.1",
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
      return mcp(request, env, ctx);
    }
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;

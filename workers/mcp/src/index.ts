import { createMcpHandler } from "agents/mcp/server";
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
      return mcp(request, env, ctx);
    }
    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;

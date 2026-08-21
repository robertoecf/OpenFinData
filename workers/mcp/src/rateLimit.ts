export const MCP_MINUTE_LIMIT = 60;
export const MCP_MINUTE_PERIOD_S = 60;
export const MCP_BURST_LIMIT = 20;
export const MCP_BURST_PERIOD_S = 10;
export const RATE_LIMITED_ERROR = "rate_limited";

export type LimitBinding = {
  limit(options: { key: string }): Promise<{ success: boolean }>;
};

export function clientKey(request: Request): string {
  const cfIp = request.headers.get("cf-connecting-ip")?.trim();
  if (cfIp) {
    return `mcp:${cfIp}`;
  }
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) {
      return `mcp:${first}`;
    }
  }
  return "mcp:unknown";
}

export function rateLimitedResponse(retryAfterSeconds: number): Response {
  return new Response(JSON.stringify({ error: RATE_LIMITED_ERROR }), {
    status: 429,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "retry-after": String(retryAfterSeconds),
    },
  });
}

export async function enforceMcpRateLimits(
  request: Request,
  minute: LimitBinding,
  burst: LimitBinding,
): Promise<Response | null> {
  const key = clientKey(request);
  const [minuteResult, burstResult] = await Promise.all([
    minute.limit({ key }),
    burst.limit({ key }),
  ]);
  if (!minuteResult.success) {
    return rateLimitedResponse(MCP_MINUTE_PERIOD_S);
  }
  if (!burstResult.success) {
    return rateLimitedResponse(MCP_BURST_PERIOD_S);
  }
  return null;
}

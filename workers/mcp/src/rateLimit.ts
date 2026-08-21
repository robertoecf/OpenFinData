export const MCP_MINUTE_LIMIT = 60;
export const MCP_MINUTE_PERIOD_S = 60;
export const MCP_BURST_LIMIT = 20;
export const MCP_BURST_PERIOD_S = 10;
export const RATE_LIMITED_ERROR = "rate_limited";

export type LimitBinding = {
  limit(options: { key: string }): Promise<{ success: boolean }>;
};

export function clientKey(request: Request): string {
  // Production Workers always set CF-Connecting-IP. Do not fall back to
  // X-Forwarded-For: that header is client-spoofable when the CF header is absent.
  const cfIp = request.headers.get("cf-connecting-ip")?.trim();
  return cfIp ? `mcp:${cfIp}` : "mcp:unknown";
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

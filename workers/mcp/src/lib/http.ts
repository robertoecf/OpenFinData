const USER_AGENT = "openfindata-mcp/0.3.1 (+https://github.com/robertoecf/OpenFinData)";

export const FETCH_TIMEOUT_MS = 15_000;
export const MAX_RESPONSE_BYTES = 2_000_000;

export class UpstreamError extends Error {
  readonly status: number;
  readonly url: string;
  constructor(status: number, url: string) {
    super(`upstream ${status} for ${url}`);
    this.status = status;
    this.url = url;
    this.name = "UpstreamError";
  }
}

export class UpstreamLimitError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UpstreamLimitError";
  }
}

export type GetJsonOptions = {
  maxBytes?: number;
  timeoutMs?: number;
};

export async function getBytes(url: string, options?: GetJsonOptions): Promise<Uint8Array> {
  const maxBytes = options?.maxBytes ?? MAX_RESPONSE_BYTES;
  const timeoutMs = options?.timeoutMs ?? FETCH_TIMEOUT_MS;
  const response = await fetch(url, {
    headers: { "user-agent": USER_AGENT },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new UpstreamError(response.status, url);
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > maxBytes) {
    throw new UpstreamLimitError(
      `upstream response too large (${buffer.byteLength} bytes, max ${maxBytes})`,
    );
  }
  return new Uint8Array(buffer);
}

export async function getJson(
  url: string,
  params?: Record<string, string | number | undefined>,
  options?: GetJsonOptions,
): Promise<unknown> {
  const target = new URL(url);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") {
        target.searchParams.set(key, String(value));
      }
    }
  }
  const maxBytes = options?.maxBytes ?? MAX_RESPONSE_BYTES;
  const timeoutMs = options?.timeoutMs ?? FETCH_TIMEOUT_MS;
  const response = await fetch(target, {
    headers: { accept: "application/json", "user-agent": USER_AGENT },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) {
    throw new UpstreamError(response.status, target.toString());
  }
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength > maxBytes) {
    throw new UpstreamLimitError(
      `upstream response too large (${buffer.byteLength} bytes, max ${maxBytes})`,
    );
  }
  return JSON.parse(new TextDecoder().decode(buffer)) as unknown;
}

export function odataValue(raw: unknown): unknown[] {
  if (Array.isArray(raw)) {
    return raw;
  }
  if (raw && typeof raw === "object" && "value" in raw) {
    const value = (raw as { value: unknown }).value;
    return Array.isArray(value) ? value : [];
  }
  return [];
}

export function jsonResult(data: unknown): { content: [{ type: "text"; text: string }] } {
  return { content: [{ type: "text", text: JSON.stringify(data) }] };
}

export function errorResult(message: string): {
  isError: true;
  content: [{ type: "text"; text: string }];
} {
  return { isError: true, content: [{ type: "text", text: message }] };
}

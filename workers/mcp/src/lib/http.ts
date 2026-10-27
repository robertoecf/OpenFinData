const USER_AGENT = "openfindata-mcp/0.3.3 (+https://github.com/robertoecf/OpenFinData)";

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

export class UpstreamFormatError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = "UpstreamFormatError";
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

/** Build the request URL.
 *
 * `URLSearchParams` serialises a space as `+` (form encoding). BCB's Olinda
 * OData gateway does not decode `+` inside a query option, so `$orderby=Data
 * desc` reaches it as `Data+desc` and it answers 400. Re-encode those spaces
 * as `%20`. A literal `+` in a value is already escaped to `%2B`, so every
 * remaining `+` came from a space.
 */
export function buildUrl(
  url: string,
  params?: Record<string, string | number | undefined>,
): URL {
  const target = new URL(url);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") {
        target.searchParams.set(key, String(value));
      }
    }
  }
  target.search = target.searchParams.toString().replace(/\+/g, "%20");
  return target;
}

export async function getJson(
  url: string,
  params?: Record<string, string | number | undefined>,
  options?: GetJsonOptions,
): Promise<unknown> {
  const target = buildUrl(url, params);
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
  return parseJsonBody(new TextDecoder().decode(buffer), target.toString());
}

/** Parse an upstream body that is contractually JSON.
 *
 * BCB's SGS gateway answers HTTP 200 with an HTML error page ("Requisicao
 * invalida!") when it is degraded or rejects the request. Surfacing the raw
 * parser message ("Unexpected token '<'") tells an agent nothing, so name the
 * real condition instead.
 */
export function parseJsonBody(body: string, url: string): unknown {
  try {
    return JSON.parse(body) as unknown;
  } catch (cause) {
    const head = body.trimStart().slice(0, 120).replace(/\s+/g, " ");
    throw new UpstreamFormatError(
      `upstream returned a non-JSON body for ${url} (likely an error page or an outage); first bytes: ${head}`,
      { cause },
    );
  }
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

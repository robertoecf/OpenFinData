/** Minimal ZIP + semicolon CSV helpers for CVM dados abertos (ISO-8859-1). */

const LOCAL_SIG = 0x04034b50;
const CENTRAL_SIG = 0x02014b50;
const LATIN1 = new TextDecoder("latin1");

function u16(buf: Uint8Array, offset: number): number {
  return buf[offset]! | (buf[offset + 1]! << 8);
}

function u32(buf: Uint8Array, offset: number): number {
  return (
    (buf[offset]! |
      (buf[offset + 1]! << 8) |
      (buf[offset + 2]! << 16) |
      (buf[offset + 3]! << 24)) >>>
    0
  );
}

async function inflateRaw(data: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

export async function zipFile(zip: Uint8Array, name: string): Promise<Uint8Array> {
  let offset = 0;
  while (offset + 30 <= zip.length) {
    const sig = u32(zip, offset);
    if (sig === CENTRAL_SIG) {
      break;
    }
    if (sig !== LOCAL_SIG) {
      throw new Error("invalid zip local header");
    }
    const method = u16(zip, offset + 8);
    const compSize = u32(zip, offset + 18);
    const nameLen = u16(zip, offset + 26);
    const extraLen = u16(zip, offset + 28);
    const nameStart = offset + 30;
    const entryName = LATIN1.decode(zip.subarray(nameStart, nameStart + nameLen));
    const dataStart = nameStart + nameLen + extraLen;
    const dataEnd = dataStart + compSize;
    if (dataEnd > zip.length) {
      throw new Error(`zip entry ${entryName} truncated`);
    }
    if (entryName === name || entryName.endsWith(`/${name}`)) {
      const payload = zip.subarray(dataStart, dataEnd);
      if (method === 0) {
        return payload;
      }
      if (method === 8) {
        return inflateRaw(payload);
      }
      throw new Error(`unsupported zip method ${method} for ${entryName}`);
    }
    offset = dataEnd;
  }
  throw new Error(`zip entry not found: ${name}`);
}

export function cnpjDigits(value: string | undefined): string {
  return (value ?? "").replace(/\D/g, "");
}

export function parseCsvRow(header: string[], line: string): Record<string, string> {
  const cells = line.split(";");
  const row: Record<string, string> = {};
  for (let i = 0; i < header.length; i++) {
    row[header[i]!] = cells[i] ?? "";
  }
  return row;
}

function lineContains(bytes: Uint8Array, needle: Uint8Array): boolean {
  if (needle.length === 0 || bytes.length < needle.length) {
    return false;
  }
  outer: for (let i = 0; i <= bytes.length - needle.length; i++) {
    for (let j = 0; j < needle.length; j++) {
      if (bytes[i + j] !== needle[j]) {
        continue outer;
      }
    }
    return true;
  }
  return false;
}

function eachCsvLine(bytes: Uint8Array, visit: (line: Uint8Array) => boolean): void {
  let start = 0;
  for (let i = 0; i <= bytes.length; i++) {
    if (i === bytes.length || bytes[i] === 10) {
      let end = i;
      if (end > start && bytes[end - 1] === 13) {
        end -= 1;
      }
      if (end > start && !visit(bytes.subarray(start, end))) {
        return;
      }
      start = i + 1;
    }
  }
}

export function scanCsv(
  bytes: Uint8Array,
  keep: (row: Record<string, string>, raw: string) => boolean,
  limit: number,
): Record<string, string>[] {
  const out: Record<string, string>[] = [];
  let header: string[] | null = null;
  eachCsvLine(bytes, (line) => {
    const raw = LATIN1.decode(line);
    if (header === null) {
      header = raw.split(";");
      return true;
    }
    const row = parseCsvRow(header, raw);
    if (keep(row, raw)) {
      out.push(row);
    }
    return out.length < limit;
  });
  return out;
}

export function scanCsvForNeedles(
  bytes: Uint8Array,
  needles: string[],
  limit: number,
): Record<string, string>[] {
  const encoded = needles.filter(Boolean).map((item) => new TextEncoder().encode(item));
  const out: Record<string, string>[] = [];
  let header: string[] | null = null;
  eachCsvLine(bytes, (line) => {
    if (header === null) {
      header = LATIN1.decode(line).split(";");
      return true;
    }
    if (!encoded.some((needle) => lineContains(line, needle))) {
      return true;
    }
    out.push(parseCsvRow(header, LATIN1.decode(line)));
    return out.length < limit;
  });
  return out;
}

export function optFloat(value: string | undefined): number | null {
  const raw = (value ?? "").trim().replace(",", ".");
  if (!raw) {
    return null;
  }
  const num = Number(raw);
  return Number.isFinite(num) ? num : null;
}

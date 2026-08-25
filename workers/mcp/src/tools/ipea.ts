import { errorResult, getJson, jsonResult, odataValue } from "../lib/http";
import ipeaCatalog from "../catalog/ipea.json";

const BASE = "http://www.ipeadata.gov.br/api/odata4";

function metadataRow(item: Record<string, unknown>) {
  return {
    sercodigo: item.SERCODIGO,
    sernome: item.SERNOME,
    sercomentario: item.SERCOMENTARIO ?? null,
    serunidade: item.SERUNIDADE ?? null,
    serperiodicidade: item.SERPERIODICIDADE ?? null,
    sertema: item.SERTTEMA ?? item.SERTEMA ?? null,
    serfonte: item.SERFONTE ?? null,
  };
}

export async function ipeaSeries(args: {
  sercodigo?: string;
  dataset?: "values" | "metadata";
  top?: number;
}) {
  if (!args.sercodigo) {
    return jsonResult(ipeaCatalog);
  }
  if (!/^[A-Za-z0-9_]+$/.test(args.sercodigo)) {
    return errorResult("invalid SERCODIGO");
  }
  if (args.dataset === "metadata") {
    const raw = await getJson(`${BASE}/Metadados('${args.sercodigo}')`);
    const items = odataValue(raw) as Record<string, unknown>[];
    if (!items.length) {
      return errorResult(`unknown SERCODIGO: ${args.sercodigo}`);
    }
    return jsonResult(metadataRow(items[0]));
  }
  const raw = await getJson(`${BASE}/ValoresSerie(SERCODIGO='${args.sercodigo}')`);
  const points = (odataValue(raw) as Record<string, unknown>[]).map((item) => ({
    sercodigo: item.SERCODIGO,
    data: item.VALDATA,
    valor: item.VALVALOR ?? null,
  }));
  const top = args.top ?? 500;
  return jsonResult(
    [...points].sort((a, b) => String(b.data).localeCompare(String(a.data))).slice(0, top),
  );
}

export async function ipeaSearch(args: { q: string; top?: number }) {
  const top = args.top ?? 25;
  const q = args.q.replaceAll("'", "''");
  const variants = [...new Set([q, q.toLowerCase(), q.toUpperCase(), titleCase(q)])];
  const parts: string[] = [];
  for (const variant of variants) {
    parts.push(`substringof('${variant}', SERNOME)`);
    parts.push(`substringof('${variant}', SERCODIGO)`);
  }
  const raw = await getJson(`${BASE}/Metadados`, {
    $top: Math.max(top * 2, top),
    $filter: parts.join(" or "),
  });
  const seen = new Set<string>();
  const out: ReturnType<typeof metadataRow>[] = [];
  for (const item of odataValue(raw) as Record<string, unknown>[]) {
    const row = metadataRow(item);
    const code = String(row.sercodigo ?? "");
    if (!code || seen.has(code)) continue;
    seen.add(code);
    out.push(row);
    if (out.length >= top) break;
  }
  return jsonResult(out);
}

function titleCase(value: string): string {
  return value.replace(/\w\S*/g, (word) => word[0].toUpperCase() + word.slice(1).toLowerCase());
}

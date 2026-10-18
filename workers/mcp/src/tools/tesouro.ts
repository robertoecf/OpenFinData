import { errorResult, getJson, jsonResult } from "../lib/http.ts";

const SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt";
const PAGE = 2000;
const MAX_PAGES_ENTES = 3;
const MAX_PAGES_REPORT = 1;
const ENTES_DEFAULT_LIMIT = 100;
const REPORT_DEFAULT_LIMIT = 2000;

async function paginate(
  path: string,
  params: Record<string, string | number | undefined>,
  maxPages: number,
): Promise<Record<string, unknown>[]> {
  const rows: Record<string, unknown>[] = [];
  for (let page = 0; page < maxPages; page += 1) {
    const raw = (await getJson(`${SICONFI}/${path}`, {
      ...params,
      limit: PAGE,
      offset: page * PAGE,
    })) as { items?: unknown; hasMore?: boolean };
    const items = Array.isArray(raw.items) ? raw.items : [];
    for (const item of items) {
      if (item && typeof item === "object") {
        rows.push(item as Record<string, unknown>);
      }
    }
    if (!raw.hasMore) break;
  }
  return rows;
}

/** Bounded payload plus the counters an agent needs to know it saw everything. */
export function envelopeBody(
  key: string,
  matched: unknown[],
  limit: number,
  hint: string,
): Record<string, unknown> {
  const rows = matched.slice(0, limit);
  const truncated = matched.length > rows.length;
  return {
    total_matched: matched.length,
    returned: rows.length,
    limit,
    truncated,
    ...(truncated ? { hint } : {}),
    [key]: rows,
  };
}

function envelope(key: string, matched: unknown[], limit: number, hint: string) {
  return jsonResult(envelopeBody(key, matched, limit, hint));
}

/** Lowercase and strip accents so "sao paulo" matches "São Paulo". */
export function fold(value: unknown): string {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

export type Ente = {
  cod_ibge: unknown;
  uf: unknown;
  instituicao: unknown;
  esfera: unknown;
  populacao: unknown;
};

/** Project SICONFI rows to the agent-facing shape, then narrow them. */
export function filterEntes(
  rows: Record<string, unknown>[],
  args: { uf?: string; esfera?: string; q?: string },
): Ente[] {
  let matched: Ente[] = rows.map((row) => ({
    cod_ibge: row.cod_ibge,
    uf: row.uf,
    instituicao: row.instituicao ?? row.ente,
    esfera: row.esfera,
    populacao: row.populacao ?? null,
  }));
  if (args.uf) {
    const uf = fold(args.uf);
    matched = matched.filter((row) => fold(row.uf) === uf);
  }
  if (args.esfera) {
    const esfera = fold(args.esfera);
    matched = matched.filter((row) => fold(row.esfera) === esfera);
  }
  if (args.q) {
    const needle = fold(args.q);
    matched = matched.filter((row) => fold(row.instituicao).includes(needle));
  }
  return matched;
}

export async function tesouroSiconfi(args: {
  report?: "rreo" | "rgf" | "entes";
  year?: number;
  period?: number;
  cod_ibge?: number;
  poder?: string;
  anexo?: string;
  uf?: string;
  q?: string;
  esfera?: string;
  limit?: number;
}) {
  const report = args.report ?? "entes";
  if (report === "entes") {
    const rows = await paginate("entes", {}, MAX_PAGES_ENTES);
    const matched = filterEntes(rows, args);
    return envelope(
      "entes",
      matched,
      args.limit ?? ENTES_DEFAULT_LIMIT,
      "narrow with uf (e.g. uf=SP), esfera (M/E/U/D) or q (name fragment), or raise limit",
    );
  }
  if (args.year === undefined || args.period === undefined || args.cod_ibge === undefined) {
    return errorResult(
      `report=${report} requires year, period, and cod_ibge ` +
        "(find cod_ibge with report=entes plus uf/q)",
    );
  }
  const limit = args.limit ?? REPORT_DEFAULT_LIMIT;
  const hint = "raise limit, or narrow with anexo";
  if (report === "rgf") {
    if (args.period < 1 || args.period > 3) {
      return errorResult("RGF period is the quadrimestre 1-3");
    }
    const rows = await paginate(
      "rgf",
      {
        an_exercicio: args.year,
        nr_periodo: args.period,
        co_tipo_demonstrativo: "RGF",
        co_poder: args.poder ?? "E",
        id_ente: args.cod_ibge,
        no_anexo: args.anexo,
      },
      MAX_PAGES_REPORT,
    );
    return envelope("rows", rows, limit, hint);
  }
  const rows = await paginate(
    "rreo",
    {
      an_exercicio: args.year,
      nr_periodo: args.period,
      co_tipo_demonstrativo: "RREO",
      id_ente: args.cod_ibge,
      no_anexo: args.anexo,
    },
    MAX_PAGES_REPORT,
  );
  return envelope("rows", rows, limit, hint);
}

import { errorResult, getJson, jsonResult } from "../lib/http";

const SICONFI = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt";
const PAGE = 2000;
const MAX_PAGES_ENTES = 3;
const MAX_PAGES_REPORT = 1;

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

export async function tesouroSiconfi(args: {
  report?: "rreo" | "rgf" | "entes";
  year?: number;
  period?: number;
  cod_ibge?: number;
  poder?: string;
  anexo?: string;
}) {
  const report = args.report ?? "entes";
  if (report === "entes") {
    const rows = await paginate("entes", {}, MAX_PAGES_ENTES);
    return jsonResult(
      rows.map((row) => ({
        cod_ibge: row.cod_ibge,
        uf: row.uf,
        instituicao: row.instituicao ?? row.ente,
        esfera: row.esfera,
        populacao: row.populacao ?? null,
      })),
    );
  }
  if (args.year === undefined || args.period === undefined || args.cod_ibge === undefined) {
    return errorResult(`report=${report} requires year, period, and cod_ibge`);
  }
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
    return jsonResult(rows.slice(0, 2000));
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
  return jsonResult(rows.slice(0, 2000));
}

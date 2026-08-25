import { errorResult, getJson, jsonResult } from "../lib/http";
import ibgeCatalog from "../catalog/ibge.json";

const BASE = "https://servicodados.ibge.gov.br/api/v3/agregados";

type IbgePoint = {
  periodo: string;
  valor: number | null;
  localidade: string;
  variavel: string;
  classificacao: string | null;
};

function parseIbge(raw: unknown): IbgePoint[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const results: IbgePoint[] = [];
  for (const varBlock of raw) {
    if (!varBlock || typeof varBlock !== "object") continue;
    const block = varBlock as {
      variavel?: string;
      resultados?: Array<{
        classificacoes?: Array<{ categoria?: Record<string, string> }>;
        series?: Array<{
          localidade?: { nome?: string };
          serie?: Record<string, string>;
        }>;
      }>;
    };
    const variavel = block.variavel ?? "";
    for (const resultado of block.resultados ?? []) {
      let classificacao: string | null = null;
      for (const classif of resultado.classificacoes ?? []) {
        for (const cat of Object.values(classif.categoria ?? {})) {
          classificacao = cat;
        }
      }
      for (const serie of resultado.series ?? []) {
        const localidade = serie.localidade?.nome ?? "Brasil";
        for (const [periodo, valorStr] of Object.entries(serie.serie ?? {})) {
          let valor: number | null = null;
          if (valorStr && valorStr !== "...") {
            const parsed = Number(valorStr);
            valor = Number.isNaN(parsed) ? null : parsed;
          }
          results.push({ periodo, valor, localidade, variavel, classificacao });
        }
      }
    }
  }
  return results;
}

export async function ibgeIndicator(args: { name?: string; periods?: number }) {
  if (!args.name) {
    return jsonResult(ibgeCatalog.indicators);
  }
  const info = (ibgeCatalog.indicators as Record<string, { agregado: number; variavel: number }>)[
    args.name
  ];
  if (!info) {
    return errorResult(`unknown indicator '${args.name}'`);
  }
  const periods = args.periods ?? 12;
  const raw = await getJson(
    `${BASE}/${info.agregado}/periodos/-${periods}/variaveis/${info.variavel}`,
    { localidades: "N1[all]" },
  );
  return jsonResult(parseIbge(raw));
}

export async function ibgeIpcaBreakdown(args: { periods?: number }) {
  const periods = args.periods ?? 6;
  const groups = Object.keys(ibgeCatalog.ipca_groups).join(",");
  const raw = await getJson(`${BASE}/7060/periodos/-${periods}/variaveis/63`, {
    localidades: "N1[all]",
    classificacao: `315[${groups}]`,
  });
  return jsonResult(parseIbge(raw));
}

import { errorResult, getJson, jsonResult, odataValue } from "../lib/http";
import sgsCatalog from "../catalog/sgs.json";
import focusIndicators from "../catalog/focus.json";

const SGS_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados";
const PTAX_URL = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata";
const FOCUS_URL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata";

type SgsPoint = { data: string; valor: number };

function parseSgs(raw: unknown): SgsPoint[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: SgsPoint[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as { data?: unknown; valor?: unknown };
    if (typeof row.data !== "string") continue;
    const valor = Number(row.valor);
    if (Number.isNaN(valor)) continue;
    out.push({ data: row.data, valor });
  }
  return out;
}

function fmtPtaxDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${month}-${day}-${year}`;
}

function fmtSgsDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

export async function bcbSeries(args: {
  code?: number;
  name?: string;
  start?: string;
  end?: string;
  last_n?: number;
}) {
  if (args.code === undefined && !args.name) {
    return jsonResult(sgsCatalog);
  }
  if (args.name) {
    const entry = (sgsCatalog as Record<string, { code: number }>)[args.name];
    if (!entry) {
      return errorResult(`unknown series '${args.name}'`);
    }
    const n = Math.min(args.last_n ?? 10, 200);
    const raw = await getJson(`${SGS_URL.replace("{code}", String(entry.code))}/ultimos/${n}`, {
      formato: "json",
    });
    return jsonResult(parseSgs(raw));
  }
  const code = args.code as number;
  const bounded = args.last_n ?? (args.start && args.end ? undefined : 10);
  if (bounded !== undefined) {
    const raw = await getJson(
      `${SGS_URL.replace("{code}", String(code))}/ultimos/${Math.min(bounded, 200)}`,
      {
        formato: "json",
      },
    );
    return jsonResult(parseSgs(raw));
  }
  const raw = await getJson(SGS_URL.replace("{code}", String(code)), {
    formato: "json",
    dataInicial: args.start ? fmtSgsDate(args.start) : undefined,
    dataFinal: args.end ? fmtSgsDate(args.end) : undefined,
  });
  return jsonResult(parseSgs(raw));
}

export async function bcbPtax(args: {
  currency?: string;
  date?: string;
  start?: string;
  end?: string;
}) {
  const currency = (args.currency ?? "USD").toUpperCase();
  if (args.start && args.end) {
    if (currency !== "USD") {
      return errorResult("range queries are USD-only; use `date` for other currencies");
    }
    const raw = await getJson(
      `${PTAX_URL}/CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)`,
      {
        "@dataInicial": `'${fmtPtaxDate(args.start)}'`,
        "@dataFinalCotacao": `'${fmtPtaxDate(args.end)}'`,
        $format: "json",
      },
    );
    return jsonResult(odataValue(raw));
  }
  const day = args.date ?? new Date().toISOString().slice(0, 10);
  if (currency === "USD") {
    const raw = await getJson(`${PTAX_URL}/CotacaoDolarDia(dataCotacao=@dataCotacao)`, {
      "@dataCotacao": `'${fmtPtaxDate(day)}'`,
      $format: "json",
    });
    return jsonResult(odataValue(raw));
  }
  const raw = await getJson(`${PTAX_URL}/CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)`, {
    "@moeda": `'${currency}'`,
    "@dataCotacao": `'${fmtPtaxDate(day)}'`,
    $format: "json",
  });
  return jsonResult(odataValue(raw));
}

function focusIndicator(name: string): string | undefined {
  const list = focusIndicators as string[];
  return list.find((item) => item.toUpperCase() === name.toUpperCase());
}

export async function bcbFocus(args: {
  indicator?: string;
  horizon?: "annual" | "monthly";
  panel?: "market" | "top5";
  top?: number;
}) {
  const indicator = args.indicator ?? "IPCA";
  const top = args.top ?? 20;
  if (indicator.trim().toLowerCase() === "list") {
    return jsonResult(focusIndicators);
  }
  if (indicator.trim().toLowerCase() === "selic") {
    const raw = await getJson(`${FOCUS_URL}/ExpectativasMercadoSelic`, {
      $top: top,
      $format: "json",
      $orderby: "Data desc",
    });
    return jsonResult(odataValue(raw));
  }
  const safe = focusIndicator(indicator);
  if (!safe) {
    return errorResult(`unknown indicator '${indicator}'`);
  }
  const horizon = args.horizon ?? "annual";
  const panel = args.panel ?? "market";
  if (panel === "top5" && horizon === "monthly") {
    return errorResult("panel=top5 is annual-only; use horizon=annual");
  }
  const endpoint =
    panel === "top5"
      ? "ExpectativasMercadoTop5Anuais"
      : horizon === "monthly"
        ? "ExpectativaMercadoMensais"
        : "ExpectativasMercadoAnuais";
  const raw = await getJson(`${FOCUS_URL}/${endpoint}`, {
    $top: top,
    $format: "json",
    $orderby: "Data desc",
    $filter: `Indicador eq '${safe}'`,
  });
  return jsonResult(odataValue(raw));
}

import { McpServer } from "@modelcontextprotocol/server";
import { z } from "zod";
import { errorResult } from "./lib/http";
import { bcbFocus, bcbPtax, bcbSeries } from "./tools/bcb";
import { ibgeIndicator, ibgeIpcaBreakdown } from "./tools/ibge";
import { ipeaSearch, ipeaSeries } from "./tools/ipea";
import { tesouroSiconfi } from "./tools/tesouro";
import { openfinanceDirectory } from "./tools/openfinance";
import { cvmFund } from "./tools/cvm";

type ToolResult = { content: [{ type: "text"; text: string }]; isError?: boolean };

function wrap<T>(run: (args: T) => Promise<ToolResult>) {
  return async (args: T) => {
    try {
      return await run(args);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return errorResult(message);
    }
  };
}

export function createServer() {
  const server = new McpServer({
    name: "openfindata",
    version: "0.3.3",
    websiteUrl: "https://openfindata.com.br",
  });

  server.registerTool(
    "bcb_series",
    {
      description:
        "BCB time series (Selic, IPCA, câmbio…): omit args to list the catalog; pass code or name to fetch.",
      inputSchema: z.strictObject({
        code: z.number().int().optional(),
        name: z.string().optional(),
        start: z.string().optional().describe("YYYY-MM-DD"),
        end: z.string().optional().describe("YYYY-MM-DD"),
        last_n: z.number().int().min(1).max(200).optional(),
      }),
    },
    wrap((args) => bcbSeries(args)),
  );

  server.registerTool(
    "bcb_ptax",
    {
      description:
        "PTAX official exchange rate. Range queries are USD-only. " +
        "Returns {currency, date|start+end, count, cotacoes}; when count is 0 a reason field says why " +
        "(non_business_day, not_published_yet, future_date, no_quote_for_date) — an empty list is not an error.",
      inputSchema: z.strictObject({
        currency: z.string().default("USD"),
        date: z.string().optional().describe("YYYY-MM-DD"),
        start: z.string().optional(),
        end: z.string().optional(),
      }),
    },
    wrap((args) => bcbPtax(args)),
  );

  server.registerTool(
    "bcb_focus",
    {
      description:
        "Boletim Focus. indicator=list for names; indicator=Selic for COPOM path; else annual/monthly.",
      inputSchema: z.strictObject({
        indicator: z.string().default("IPCA"),
        horizon: z.enum(["annual", "monthly"]).default("annual"),
        panel: z.enum(["market", "top5"]).default("market"),
        top: z.number().int().min(1).max(100).default(20),
      }),
    },
    wrap((args) => bcbFocus(args)),
  );

  server.registerTool(
    "ibge_indicator",
    {
      description: "IBGE economic indicators. Omit name to list the catalog.",
      inputSchema: z.strictObject({
        name: z.string().optional(),
        periods: z.number().int().min(1).max(120).default(12),
      }),
    },
    wrap((args) => ibgeIndicator(args)),
  );

  server.registerTool(
    "ibge_ipca_breakdown",
    {
      description: "IPCA monthly variation by major groups (not in BCB SGS).",
      inputSchema: z.strictObject({
        periods: z.number().int().min(1).max(60).default(6),
      }),
    },
    wrap((args) => ibgeIpcaBreakdown(args)),
  );

  server.registerTool(
    "ipea_series",
    {
      description: "IPEA series. Omit sercodigo for the curated catalog.",
      inputSchema: z.strictObject({
        sercodigo: z.string().optional(),
        dataset: z.enum(["values", "metadata"]).default("values"),
        top: z.number().int().min(1).max(500).optional(),
      }),
    },
    wrap((args) => ipeaSeries(args)),
  );

  server.registerTool(
    "ipea_search",
    {
      description: "Full-text search across the IPEA catalog (~8k series).",
      inputSchema: z.strictObject({
        q: z.string().min(2),
        top: z.number().int().min(1).max(200).default(25),
      }),
    },
    wrap((args) => ipeaSearch(args)),
  );

  server.registerTool(
    "tesouro_siconfi",
    {
      description:
        "SICONFI public-finance reports. Start with report=entes to resolve a cod_ibge, " +
        "narrowing with uf/esfera/q instead of pulling all ~5.6k entes. " +
        "Returns {total_matched, returned, limit, truncated, upstream_complete, entes|rows}: when truncated is true you did NOT see everything, and when upstream_complete is false total_matched counts only the rows fetched.",
      inputSchema: z.strictObject({
        report: z.enum(["rreo", "rgf", "entes"]).default("entes"),
        year: z.number().int().min(2013).optional(),
        period: z.number().int().min(1).max(6).optional(),
        cod_ibge: z.number().int().optional(),
        poder: z.string().default("E"),
        anexo: z.string().optional(),
        uf: z.string().length(2).optional().describe("entes: filter by state, e.g. SP"),
        esfera: z.string().optional().describe("entes: M municipal, E estadual, U federal, D distrital"),
        q: z.string().optional().describe("entes: accent-insensitive name fragment"),
        limit: z.number().int().min(1).max(2000).optional()
          .describe("rows in THIS response; entes default 100, reports default 2000, hard cap 2000"),
      }),
    },
    wrap((args) => tesouroSiconfi(args)),
  );

  server.registerTool(
    "cvm_fund",
    {
      description:
        "CVM open-fund official layer (never Mais Retorno; no Sharpe/CAGR/drawdown). " +
        "Mais Retorno data mapping: search_assets/get_asset_info/list_fund_structure/get_fund_class_subclass → dataset=catalog " +
        "(q matches fundo, classe and subclasse names; classes[].subclasses are different investments — do not pick a FIDC série). " +
        "get_quotes → dataset=daily (INF_DIARIO; omit year/month for latest; months=1..12 lookback or start/end YYYY-MM-DD, max 12 months; " +
        "single-class 555→175 continuation is stitched; report served[].nicename/class/subclass actually returned). " +
        "get_available_wallets → dataset=periods product=CDA. get_wallet_detail → dataset=holdings (omit year/month for latest CDA; CONFID is sigilo).",
      inputSchema: z.strictObject({
        dataset: z.enum(["catalog", "daily", "holdings", "periods"]).default("catalog"),
        cnpj: z.string().optional().describe("Fund or class CNPJ, punctuated or digits"),
        q: z.string().optional().describe("catalog: name fragment (fundo, classe or subclasse)"),
        year: z.number().int().min(2018).optional(),
        month: z.number().int().min(1).max(12).optional(),
        months: z
          .number()
          .int()
          .min(1)
          .max(12)
          .optional()
          .describe("daily: lookback months including the end month (max 12; page longer windows)"),
        start: z.string().optional().describe("daily: YYYY-MM-DD inclusive start (use with end)"),
        end: z.string().optional().describe("daily: YYYY-MM-DD inclusive end (use with start)"),
        id_subclasse: z.string().optional().describe("daily: keep only this CVM série; do not guess"),
        compact: z.boolean().optional().describe("daily: served[].dates + served[].vl_quota instead of series[]"),
        product: z.enum(["CDA", "INF_DIARIO"]).optional().describe("periods: which directory to list"),
        blocks: z
          .string()
          .optional()
          .describe("holdings: comma list such as BLC_1,BLC_4 (BLC_1..8, CONFID, PL, FIE)"),
        limit: z.number().int().min(1).max(2000).optional(),
      }),
    },
    wrap((args) => cvmFund(args)),
  );

  server.registerTool(
    "openfinance_directory",
    {
      description: "Open Finance Brasil Directory (public discovery only, no customer data).",
      inputSchema: z.strictObject({
        dataset: z.enum(["participants", "endpoints", "resources", "roles"]).default("participants"),
        role: z.string().optional(),
        status: z.string().optional(),
        api_family: z.string().optional(),
        q: z.string().min(2).optional(),
        limit: z.number().int().min(1).max(1000).default(100),
      }),
    },
    wrap((args) => openfinanceDirectory(args)),
  );

  return server;
}

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
    version: "0.3.1",
    websiteUrl: "https://openfindata.com.br",
  });

  server.registerTool(
    "bcb_series",
    {
      description:
        "BCB time series (Selic, IPCA, câmbio…): omit args to list the catalog; pass code or name to fetch.",
      inputSchema: {
        code: z.number().int().optional(),
        name: z.string().optional(),
        start: z.string().optional().describe("YYYY-MM-DD"),
        end: z.string().optional().describe("YYYY-MM-DD"),
        last_n: z.number().int().min(1).max(200).optional(),
      },
    },
    wrap((args) => bcbSeries(args)),
  );

  server.registerTool(
    "bcb_ptax",
    {
      description: "PTAX official exchange rate. Range queries are USD-only.",
      inputSchema: {
        currency: z.string().default("USD"),
        date: z.string().optional().describe("YYYY-MM-DD"),
        start: z.string().optional(),
        end: z.string().optional(),
      },
    },
    wrap((args) => bcbPtax(args)),
  );

  server.registerTool(
    "bcb_focus",
    {
      description:
        "Boletim Focus. indicator=list for names; indicator=Selic for COPOM path; else annual/monthly.",
      inputSchema: {
        indicator: z.string().default("IPCA"),
        horizon: z.enum(["annual", "monthly"]).default("annual"),
        panel: z.enum(["market", "top5"]).default("market"),
        top: z.number().int().min(1).max(100).default(20),
      },
    },
    wrap((args) => bcbFocus(args)),
  );

  server.registerTool(
    "ibge_indicator",
    {
      description: "IBGE economic indicators. Omit name to list the catalog.",
      inputSchema: {
        name: z.string().optional(),
        periods: z.number().int().min(1).max(120).default(12),
      },
    },
    wrap((args) => ibgeIndicator(args)),
  );

  server.registerTool(
    "ibge_ipca_breakdown",
    {
      description: "IPCA monthly variation by major groups (not in BCB SGS).",
      inputSchema: {
        periods: z.number().int().min(1).max(60).default(6),
      },
    },
    wrap((args) => ibgeIpcaBreakdown(args)),
  );

  server.registerTool(
    "ipea_series",
    {
      description: "IPEA series. Omit sercodigo for the curated catalog.",
      inputSchema: {
        sercodigo: z.string().optional(),
        dataset: z.enum(["values", "metadata"]).default("values"),
        top: z.number().int().min(1).max(500).optional(),
      },
    },
    wrap((args) => ipeaSeries(args)),
  );

  server.registerTool(
    "ipea_search",
    {
      description: "Full-text search across the IPEA catalog (~8k series).",
      inputSchema: {
        q: z.string().min(2),
        top: z.number().int().min(1).max(200).default(25),
      },
    },
    wrap((args) => ipeaSearch(args)),
  );

  server.registerTool(
    "tesouro_siconfi",
    {
      description: "SICONFI public-finance reports. Start with report=entes.",
      inputSchema: {
        report: z.enum(["rreo", "rgf", "entes"]).default("entes"),
        year: z.number().int().min(2013).optional(),
        period: z.number().int().min(1).max(6).optional(),
        cod_ibge: z.number().int().optional(),
        poder: z.string().default("E"),
        anexo: z.string().optional(),
      },
    },
    wrap((args) => tesouroSiconfi(args)),
  );

  server.registerTool(
    "cvm_fund",
    {
      description:
        "CVM open-ended funds (condomínio aberto). catalog: cadastral RCVM 175 by CNPJ or name. daily: INF_DIARIO cota/PL/cotistas for one month. Not CDA carteira (separate delayed feed). Not Mais Retorno.",
      inputSchema: {
        dataset: z.enum(["catalog", "daily"]).default("catalog"),
        cnpj: z.string().optional().describe("Fund CNPJ, punctuated or digits"),
        q: z.string().optional().describe("catalog: name fragment when CNPJ is unknown"),
        year: z.number().int().min(2021).optional(),
        month: z.number().int().min(1).max(12).optional(),
        limit: z.number().int().min(1).max(2000).optional(),
      },
    },
    wrap((args) => cvmFund(args)),
  );

  server.registerTool(
    "openfinance_directory",
    {
      description: "Open Finance Brasil Directory (public discovery only, no customer data).",
      inputSchema: {
        dataset: z.enum(["participants", "endpoints", "resources", "roles"]).default("participants"),
        role: z.string().optional(),
        status: z.string().optional(),
        api_family: z.string().optional(),
        q: z.string().min(2).optional(),
        limit: z.number().int().min(1).max(1000).default(100),
      },
    },
    wrap((args) => openfinanceDirectory(args)),
  );

  return server;
}

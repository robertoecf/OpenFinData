(() => {
  // Third-party chart engine notice kept in source, not duplicated in the UI:
  // TradingView Lightweight Charts™ Copyright (с) 2025 TradingView, Inc.
  // https://www.tradingview.com/
  //
  // Keep `layout.attributionLogo` disabled only while the page footer provides
  // a visible link to tradingview.com, as required by the upstream docs.
  const root = document.querySelector("#chart-root");
  if (!root) return;

  const BRAND = {
    ink: "#07132c",
    muted: "#42526f",
    line: "rgba(0, 39, 118, 0.16)",
    grid: "rgba(0, 39, 118, 0.1)",
    blue: "#0050ff",
    green: "#00a859",
    orange: "#ff7a1a",
    red: "#ef4444",
    white: "#ffffff",
  };
  const PRIMARY_SOURCE = "Dados Abertos de Mercado (findata-br)";
  const MAX_POINTS = 5000;
  const REQUEST_TIMEOUT_MS = 15000;
  const ALLOWED_ENDPOINT_PREFIXES = [
    "/bcb/series/",
    "/ibge/indicators/",
    "/ipea/series/",
  ];

  const isoDate = (date) => date.toISOString().slice(0, 10);

  const monthsAgo = (months) => {
    const date = new Date();
    date.setMonth(date.getMonth() - months);
    return date;
  };

  const bcbSeriesEndpoint = (code, months) => {
    const start = isoDate(monthsAgo(months));
    const end = isoDate(new Date());
    return `/bcb/series/code/${code}?start=${start}&end=${end}`;
  };

  const endpointValue = (preset) => (
    typeof preset.endpoint === "function" ? preset.endpoint() : preset.endpoint
  );

  const extractionTimestamp = () => {
    const formatted = new Intl.DateTimeFormat("pt-BR", {
      timeZone: "America/Sao_Paulo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(new Date());
    return `${formatted} BRT`;
  };

  const PRESETS = [
    {
      id: "bcb-selic",
      label: "BCB SGS 432 — Selic",
      endpoint: () => bcbSeriesEndpoint(432, 24),
      field: "valor",
      title: "Taxa Selic",
      source: "BCB SGS 432",
      color: BRAND.orange,
    },
    {
      id: "bcb-ipca",
      label: "BCB SGS 433 — IPCA mensal",
      endpoint: () => bcbSeriesEndpoint(433, 24),
      field: "valor",
      title: "IPCA mensal",
      source: "BCB SGS 433",
      color: BRAND.blue,
    },
    {
      id: "ipea-selic-over",
      label: "IPEA — Selic over mensal",
      endpoint: "/ipea/series/BM12_TJOVER12?top=160",
      field: "valor",
      title: "Selic over acumulada no mês",
      source: "IPEA Data BM12_TJOVER12",
      color: BRAND.orange,
    },
    {
      id: "ibge-ipca",
      label: "IBGE — IPCA variação mensal",
      endpoint: "/ibge/indicators/ipca_mensal?periods=48",
      field: "valor",
      title: "IPCA mensal — IBGE",
      source: "IBGE Agregados 7060/63",
      color: BRAND.blue,
    },
  ];

  const DATE_KEYS = [
    "date",
    "data",
    "periodo",
    "data_hora_cotacao",
    "dataHoraCotacao",
    "VALDATA",
  ];
  const VALUE_KEYS = [
    "valor",
    "value",
    "close",
    "adj_close",
    "preco",
    "cotacao_venda",
    "cotacaoVenda",
    "open",
    "volume",
  ];

  const nodes = {
    form: document.querySelector("[data-chart-form]"),
    preset: document.querySelector("[data-chart-preset]"),
    endpoint: document.querySelector("[data-chart-url]"),
    field: document.querySelector("[data-chart-field]"),
    title: document.querySelector("[data-chart-title]"),
    source: document.querySelector("[data-chart-source]"),
    status: document.querySelector("[data-chart-status]"),
    summary: document.querySelector("[data-chart-summary]"),
    extracted: document.querySelector("[data-chart-extracted]"),
    cutoff: document.querySelector("[data-chart-cutoff]"),
    sourceNote: document.querySelector("[data-chart-source-note]"),
  };

  let chart = null;

  const setStatus = (message, kind = "info") => {
    if (!nodes.status) return;
    nodes.status.textContent = message;
    nodes.status.dataset.kind = kind;
  };

  const activePreset = () => PRESETS.find((preset) => preset.id === nodes.preset?.value) || PRESETS[0];

  const setPreset = (preset) => {
    nodes.endpoint.value = endpointValue(preset);
    nodes.field.value = preset.field || "";
    nodes.title.textContent = preset.title;
    nodes.source.textContent = preset.source;
    if (nodes.sourceNote) {
      nodes.sourceNote.innerHTML = `<strong>Fontes dos dados.</strong> Fonte primária/curadoria: <a href="https://github.com/robertoecf/findata-br">${PRIMARY_SOURCE}</a>. Subsets originais: ${preset.source}.`;
    }
  };

  const setupControls = () => {
    if (!nodes.preset || !nodes.endpoint || !nodes.field) return;
    nodes.preset.innerHTML = PRESETS.map(
      (preset) => `<option value="${preset.id}">${preset.label}</option>`,
    ).join("");
    setPreset(PRESETS[0]);
    nodes.preset.addEventListener("change", () => setPreset(activePreset()));
  };

  const assertAllowedEndpoint = (endpoint) => {
    if (!ALLOWED_ENDPOINT_PREFIXES.some((prefix) => endpoint.startsWith(prefix))) {
      throw new Error("Labs aceita apenas endpoints temporais leves de BCB, IBGE e IPEA.");
    }
  };

  const normalizeEndpoint = (value) => {
    const trimmed = value.trim();
    if (!trimmed) throw new Error("Informe um endpoint.");
    const rawEndpoint = trimmed.startsWith("http://") || trimmed.startsWith("https://")
      ? trimmed
      : trimmed.startsWith("/")
        ? trimmed
        : `/${trimmed}`;
    const url = new URL(rawEndpoint, window.location.origin);
    if (url.origin !== window.location.origin) {
      throw new Error("Use endpoints do próprio findata-br para evitar CORS e fontes opacas.");
    }
    const endpoint = `${url.pathname}${url.search}`;
    assertAllowedEndpoint(endpoint);
    return endpoint;
  };

  const recordsFrom = (payload) => {
    if (Array.isArray(payload)) return payload;
    if (!payload || typeof payload !== "object") return null;
    for (const key of ["points", "data", "results", "value", "items"]) {
      if (Array.isArray(payload[key])) return payload[key];
    }
    return null;
  };

  const timestampFromDate = (date) => {
    if (Number.isNaN(date.getTime())) return null;
    return Math.floor(date.getTime() / 1000);
  };

  const parseTime = (value) => {
    if (typeof value === "number") {
      const date = new Date(value > 1e11 ? value : value * 1000);
      return timestampFromDate(date);
    }
    if (typeof value !== "string") return null;
    const text = String(value).trim();
    if (/^\d{10,13}$/.test(text)) {
      const timestamp = Number(text);
      const date = new Date(timestamp > 1e11 ? timestamp : timestamp * 1000);
      return timestampFromDate(date);
    }

    let match = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (match) return `${match[3]}-${match[2]}-${match[1]}`;

    match = text.match(/^(\d{4})(\d{2})$/);
    if (match) return `${match[1]}-${match[2]}-01`;

    match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (match) return `${match[1]}-${match[2]}-${match[3]}`;

    match = text.match(/^(\d{4})-(\d{2})-(\d{2})T00:00:00/);
    if (match) return `${match[1]}-${match[2]}-${match[3]}`;

    const parsed = new Date(text);
    return timestampFromDate(parsed);
  };

  const asNumber = (value) => {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value !== "string") return null;
    const text = value.trim();
    if (!text) return null;
    const normalized = /^-?\d{1,3}(\.\d{3})+,\d+$/.test(text)
      ? text.replace(/\./g, "").replace(",", ".")
      : text.replace(",", ".");
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const firstKey = (record, keys) => keys.find((key) => record[key] !== undefined);

  const chooseValueKey = (records, requestedKey) => {
    if (requestedKey) return requestedKey;
    const sample = records.find((record) => record && typeof record === "object");
    if (!sample) return null;
    const known = firstKey(sample, VALUE_KEYS);
    if (known) return known;
    return Object.keys(sample).find((key) => asNumber(sample[key]) !== null) || null;
  };

  const hasOhlc = (record) => ["open", "high", "low", "close"].every((key) => record[key] !== undefined);

  const normalizeData = (payload, options) => {
    const records = recordsFrom(payload);
    if (!records || !records.length) {
      throw new Error("Endpoint sem lista de registros para plotar.");
    }

    const firstRecord = records.find((record) => record && typeof record === "object");
    if (!firstRecord) throw new Error("Registros sem campos nomeados.");

    const dateKey = firstKey(firstRecord, DATE_KEYS);
    if (!dateKey) throw new Error("Não encontrei campo de data conhecido.");

    const shouldUseCandles = options.type === "candlestick" || (!options.field && hasOhlc(firstRecord));
    const valueKey = chooseValueKey(records, options.field);
    const deduped = new Map();

    for (const record of records) {
      if (!record || typeof record !== "object") continue;
      const time = parseTime(record[dateKey]);
      if (!time) continue;

      if (shouldUseCandles && hasOhlc(record)) {
        const open = asNumber(record.open);
        const high = asNumber(record.high);
        const low = asNumber(record.low);
        const close = asNumber(record.close);
        if ([open, high, low, close].every((value) => value !== null)) {
          deduped.set(time, { time, open, high, low, close });
        }
        continue;
      }

      const value = valueKey ? asNumber(record[valueKey]) : null;
      if (value !== null) deduped.set(time, { time, value });
    }

    const data = Array.from(deduped.values()).sort((a, b) => {
      if (typeof a.time === "number" && typeof b.time === "number") {
        return a.time - b.time;
      }
      return String(a.time).localeCompare(String(b.time));
    });
    if (!data.length) throw new Error("Nenhum ponto com data e valor numérico foi encontrado.");
    if (data.length > MAX_POINTS) {
      throw new Error(`Endpoint retornou ${data.length} pontos; use um recorte menor que ${MAX_POINTS}.`);
    }

    return {
      data,
      kind: shouldUseCandles ? "candlestick" : "line",
      valueKey,
      dateKey,
      hasIntraday: data.some((point) => typeof point.time === "number"),
    };
  };

  const makeChart = (normalized) => {
    if (chart) chart.remove();
    chart = LightweightCharts.createChart(root, {
      autoSize: true,
      height: 500,
      layout: {
        attributionLogo: false,
        background: { color: BRAND.white },
        textColor: BRAND.muted,
      },
      grid: {
        horzLines: { color: BRAND.grid },
        vertLines: { visible: false },
      },
      rightPriceScale: { borderColor: BRAND.line },
      timeScale: { borderColor: BRAND.line, timeVisible: normalized.hasIntraday },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });
    return chart;
  };

  const renderSeries = (normalized, options) => {
    const nextChart = makeChart(normalized);
    if (normalized.kind === "candlestick") {
      const series = nextChart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: BRAND.green,
        downColor: BRAND.red,
        borderVisible: false,
        wickUpColor: BRAND.green,
        wickDownColor: BRAND.red,
      });
      series.setData(normalized.data);
    } else {
      const series = nextChart.addSeries(LightweightCharts.LineSeries, {
        color: options.color || BRAND.blue,
        lineWidth: 3,
        priceLineVisible: false,
      });
      series.setData(normalized.data);
    }
    nextChart.timeScale().fitContent();
  };

  const load = async () => {
    if (!window.LightweightCharts) {
      throw new Error("Biblioteca de gráficos não carregou. Verifique conexão com o CDN.");
    }

    const preset = activePreset();
    const endpoint = normalizeEndpoint(nodes.endpoint.value);
    const field = nodes.field.value.trim();
    const presetEndpoint = endpointValue(preset);
    const usesPresetEndpoint = endpoint === presetEndpoint;
    const options = usesPresetEndpoint
      ? { ...preset, endpoint: presetEndpoint, field: field || preset.field || "" }
      : { endpoint, field, title: endpoint, source: "Endpoint findata-br" };

    setStatus("Buscando endpoint…");
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    let payload;
    try {
      const response = await fetch(endpoint, {
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Endpoint retornou HTTP ${response.status}.`);
      payload = await response.json();
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new Error("Endpoint demorou demais para o Labs. Use um recorte menor.");
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
    const normalized = normalizeData(payload, options);
    renderSeries(normalized, options);

    const first = normalized.data[0]?.time;
    const last = normalized.data[normalized.data.length - 1]?.time;
    nodes.title.textContent = options.title || endpoint;
    nodes.source.textContent = options.source || "Endpoint findata-br";
    if (nodes.extracted) {
      nodes.extracted.textContent = extractionTimestamp();
    }
    if (nodes.cutoff) nodes.cutoff.textContent = `${first} → ${last}`;
    if (nodes.sourceNote) {
      nodes.sourceNote.innerHTML = `<strong>Fontes dos dados.</strong> Fonte primária/curadoria: <a href="https://github.com/robertoecf/findata-br">${PRIMARY_SOURCE}</a>. Subsets originais: ${options.source || "endpoint findata-br"}.`;
    }
    const auditUrl = new URL(endpoint, window.location.origin);
    const auditPath = `${auditUrl.pathname}${auditUrl.search}`;
    const auditLink = document.createElement("a");
    auditLink.href = auditPath;
    auditLink.textContent = "JSON auditável";
    nodes.summary.replaceChildren(
      auditLink,
      document.createTextNode(
        ` · ${normalized.data.length} pontos · ${first} a ${last} · data=${normalized.dateKey} · valor=${normalized.valueKey || "OHLC"}`,
      ),
    );
    setStatus("Série plotada.", "ok");
  };

  const bindForm = () => {
    nodes.form?.addEventListener("submit", (event) => {
      event.preventDefault();
      load().catch((error) => setStatus(error.message, "error"));
    });
  };

  setupControls();
  bindForm();
  load().catch((error) => setStatus(error.message, "error"));
})();

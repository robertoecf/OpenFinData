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
  const PRIMARY_SOURCE = "Dados Financeiros Abertos (openfindata)";
  const CHART_SCRIPT = "src/findata/web/static/chart-explorer.js";
  const CHART_RENDERER = "TradingView Lightweight Charts 5.2.0";
  const MAX_POINTS = 5000;
  const REQUEST_TIMEOUT_MS = 15000;
  const ALLOWED_ENDPOINT_PREFIXES = [
    "/bcb/series/",
    "/ibge/indicators/",
    "/ipea/series/",
    "/b3/indices/",
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

  const seriesEndpointValue = (series) => (
    typeof series.endpoint === "function" ? series.endpoint() : series.endpoint
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
      frequency: "diária",
      color: BRAND.orange,
    },
    {
      id: "bcb-ipca",
      label: "BCB SGS 433 — IPCA mensal",
      endpoint: () => bcbSeriesEndpoint(433, 24),
      field: "valor",
      title: "IPCA mensal",
      source: "BCB SGS 433",
      frequency: "mensal",
      color: BRAND.orange,
    },
    {
      id: "ipea-selic-over",
      label: "IPEA — Selic over mensal",
      endpoint: "/ipea/series/BM12_TJOVER12?top=160",
      field: "valor",
      title: "Selic over acumulada no mês",
      source: "IPEA Data BM12_TJOVER12",
      frequency: "mensal",
      color: BRAND.orange,
    },
    {
      id: "ibge-ipca",
      label: "IBGE — IPCA variação mensal",
      endpoint: "/ibge/indicators/ipca_mensal?periods=48",
      field: "valor",
      title: "IPCA mensal — IBGE",
      source: "IBGE Agregados 7060/63",
      frequency: "mensal",
      color: BRAND.orange,
    },
    {
      id: "b3-ibov-monthly",
      label: "B3 — Ibovespa mensal",
      endpoint: () => {
        const start = isoDate(monthsAgo(120));
        const end = isoDate(new Date());
        return `/b3/indices/IBOV/monthly?start=${start}&end=${end}`;
      },
      field: "close",
      title: "Ibovespa mensal",
      source: "B3 IndexStatisticsProxy",
      frequency: "mensal",
      color: BRAND.blue,
    },
    {
      id: "selic-meta-vs-ibov",
      label: "Selic Meta vs Ibovespa",
      endpoint: () => bcbSeriesEndpoint(4189, 120),
      field: "",
      title: "Selic Meta vs Ibovespa",
      source: "BCB SGS 4189 + B3 IndexStatisticsProxy",
      frequency: "Selic diária; Ibovespa mensal",
      series: [
        {
          title: "Selic Meta (% a.a.)",
          endpoint: () => bcbSeriesEndpoint(4189, 120),
          field: "valor",
          source: "BCB SGS 4189",
          color: BRAND.orange,
          priceScaleId: "left",
        },
        {
          title: "Ibovespa (pontos)",
          endpoint: () => {
            const start = isoDate(monthsAgo(120));
            const end = isoDate(new Date());
            return `/b3/indices/IBOV/monthly?start=${start}&end=${end}`;
          },
          field: "close",
          source: "B3 IndexStatisticsProxy",
          color: BRAND.blue,
          priceScaleId: "right",
        },
      ],
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
      const subsetSource = preset.series
        ? preset.series.map((series) => series.source).join("; ")
        : preset.source;
      nodes.sourceNote.innerHTML = `<strong>Fontes dos dados.</strong> Fonte primária/curadoria: <a href="https://github.com/robertoecf/openfindata">${PRIMARY_SOURCE}</a>. Subsets originais: ${subsetSource}.`;
    }
  };

  const setupControls = () => {
    if (!nodes.preset || !nodes.endpoint || !nodes.field) return;
    nodes.preset.innerHTML = PRESETS.map(
      (preset) => `<option value="${preset.id}">${preset.label}</option>`,
    ).join("");
    const requestedPreset = new URLSearchParams(window.location.search).get("preset");
    const initialPreset = PRESETS.find((preset) => preset.id === requestedPreset) || PRESETS[0];
    nodes.preset.value = initialPreset.id;
    setPreset(initialPreset);
    nodes.preset.addEventListener("change", () => setPreset(activePreset()));
  };

  const assertAllowedEndpoint = (endpoint) => {
    if (!ALLOWED_ENDPOINT_PREFIXES.some((prefix) => endpoint.startsWith(prefix))) {
      throw new Error("Labs aceita apenas endpoints temporais leves de BCB, IBGE, IPEA e B3.");
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
      throw new Error("Use endpoints do próprio openfindata para evitar CORS e fontes opacas.");
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

  const isValidDateParts = (year, month, day) => {
    const y = Number(year);
    const m = Number(month);
    const d = Number(day);
    if (y < 1900 || y > 2200 || m < 1 || m > 12 || d < 1 || d > 31) return false;
    const date = new Date(Date.UTC(y, m - 1, d));
    return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
  };

  const parseCompactPeriod = (text) => {
    let match = text.match(/^(\d{4})(\d{2})(\d{2})$/);
    if (match && isValidDateParts(match[1], match[2], match[3])) {
      return `${match[1]}-${match[2]}-${match[3]}`;
    }

    match = text.match(/^(\d{4})(\d{2})$/);
    if (match && isValidDateParts(match[1], match[2], "01")) return `${match[1]}-${match[2]}-01`;

    return null;
  };

  const parseUnixTimestamp = (text, { allowShortSeconds = false } = {}) => {
    if (!/^\d+$/.test(text)) return null;
    const isSeconds = text.length === 10 || (allowShortSeconds && (text === "0" || text.length <= 9));
    const isMilliseconds = text.length >= 12 && text.length <= 13;
    if (!isSeconds && !isMilliseconds) return null;
    const timestamp = Number(text);
    if (!Number.isSafeInteger(timestamp)) return null;
    const date = new Date(isMilliseconds ? timestamp : timestamp * 1000);
    return timestampFromDate(date);
  };

  const parseTime = (value) => {
    const text = String(value).trim();
    const compactPeriod = parseCompactPeriod(text);
    if (compactPeriod) return compactPeriod;

    if (typeof value === "number") {
      return parseUnixTimestamp(text, { allowShortSeconds: true });
    }
    if (typeof value !== "string") return null;
    const unixTimestamp = parseUnixTimestamp(text);
    if (unixTimestamp !== null) return unixTimestamp;

    let match = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (match && isValidDateParts(match[3], match[2], match[1])) return `${match[3]}-${match[2]}-${match[1]}`;

    match = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (match && isValidDateParts(match[1], match[2], match[3])) return `${match[1]}-${match[2]}-${match[3]}`;

    match = text.match(/^(\d{4})-(\d{2})-(\d{2})T00:00:00/);
    if (match && isValidDateParts(match[1], match[2], match[3])) return `${match[1]}-${match[2]}-${match[3]}`;

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

  const timeSortValue = (time) => {
    if (typeof time === "number") return time;
    return timestampFromDate(new Date(`${time}T00:00:00Z`));
  };

  const dedupeByTime = (data) => {
    const deduped = new Map();
    for (const point of data) deduped.set(point.time, point);
    return Array.from(deduped.values());
  };

  const normalizeMixedTimes = (data) => {
    const hasIntraday = data.some((point) => typeof point.time === "number");
    if (!hasIntraday) return { data, hasIntraday };
    const normalizedData = [];
    for (const point of data) {
      if (typeof point.time === "number") {
        normalizedData.push(point);
        continue;
      }
      const time = timeSortValue(point.time);
      if (time !== null) normalizedData.push({ ...point, time });
    }
    return {
      hasIntraday,
      data: normalizedData,
    };
  };

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

    const normalizedTime = normalizeMixedTimes(Array.from(deduped.values()));
    const data = dedupeByTime(normalizedTime.data).sort((a, b) => (
      normalizedTime.hasIntraday ? a.time - b.time : a.time.localeCompare(b.time)
    ));
    if (!data.length) throw new Error("Nenhum ponto com data e valor numérico foi encontrado.");
    if (data.length > MAX_POINTS) {
      throw new Error(`Endpoint retornou ${data.length} pontos; use um recorte menor que ${MAX_POINTS}.`);
    }

    return {
      data,
      kind: shouldUseCandles ? "candlestick" : "line",
      valueKey,
      dateKey,
      hasIntraday: normalizedTime.hasIntraday,
    };
  };

  const makeChart = (normalized, { showLeftScale = false } = {}) => {
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
      leftPriceScale: { borderColor: BRAND.line, visible: showLeftScale },
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
        priceScaleId: options.priceScaleId || "right",
      });
      series.setData(normalized.data);
    }
    nextChart.timeScale().fitContent();
  };

  const fetchJson = async (endpoint) => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(endpoint, {
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Endpoint retornou HTTP ${response.status}.`);
      return await response.json();
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new Error("Endpoint demorou demais para o Labs. Use um recorte menor.");
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  };

  const renderComparisonSeries = (items) => {
    const nextChart = makeChart(
      { hasIntraday: items.some((item) => item.normalized.hasIntraday) },
      { showLeftScale: items.some((item) => item.options.priceScaleId === "left") },
    );
    for (const item of items) {
      if (item.normalized.kind !== "line") {
        throw new Error("Comparações aceitam apenas séries de linha.");
      }
      const series = nextChart.addSeries(LightweightCharts.LineSeries, {
        color: item.options.color || BRAND.blue,
        lineWidth: 3,
        priceLineVisible: false,
        priceScaleId: item.options.priceScaleId || "right",
        title: item.options.title,
      });
      series.setData(item.normalized.data);
    }
    nextChart.timeScale().fitContent();
  };

  const sourceList = (options) => (
    options.series ? options.series.map((series) => series.source).join("; ") : options.source
  );

  const loadComparison = async (options) => {
    setStatus("Buscando endpoints…");
    const items = [];
    for (const seriesOptions of options.series) {
      const endpoint = normalizeEndpoint(seriesEndpointValue(seriesOptions));
      const payload = await fetchJson(endpoint);
      items.push({
        endpoint,
        options: { ...seriesOptions, endpoint },
        normalized: normalizeData(payload, seriesOptions),
      });
    }
    renderComparisonSeries(items);

    const first = items.map((item) => item.normalized.data[0]?.time).filter(Boolean).sort()[0];
    const last = items.map((item) => item.normalized.data.at(-1)?.time).filter(Boolean).sort().at(-1);
    const points = items.reduce((total, item) => total + item.normalized.data.length, 0);
    nodes.title.textContent = options.title;
    nodes.source.textContent = options.source;
    if (nodes.extracted) nodes.extracted.textContent = extractionTimestamp();
    if (nodes.cutoff) nodes.cutoff.textContent = `${first} → ${last}`;
    if (nodes.sourceNote) {
      nodes.sourceNote.innerHTML = `<strong>Fontes dos dados.</strong> Fonte primária/curadoria: <a href="https://github.com/robertoecf/openfindata">${PRIMARY_SOURCE}</a>. Subsets originais: ${sourceList(options)}.`;
    }
    const links = [];
    items.forEach((item, index) => {
      if (index > 0) links.push(document.createTextNode(" + "));
      const link = document.createElement("a");
      link.href = item.endpoint;
      link.textContent = item.options.title;
      links.push(link);
    });
    nodes.summary.replaceChildren(
      document.createTextNode("JSON auditável: "),
      ...links,
      document.createTextNode(
        ` · Script: ${CHART_SCRIPT} · Renderer: ${CHART_RENDERER} · Frequência: ${options.frequency} · ${points} pontos · ${first} a ${last} · Escalas: Selic à esquerda, Ibovespa à direita`,
      ),
    );
    setStatus("Séries plotadas.", "ok");
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
      : { endpoint, field, title: endpoint, source: "Endpoint openfindata", frequency: "não inferida" };
    if (options.series) {
      await loadComparison(options);
      return;
    }

    setStatus("Buscando endpoint…");
    const payload = await fetchJson(endpoint);
    const normalized = normalizeData(payload, options);
    renderSeries(normalized, options);

    const first = normalized.data[0]?.time;
    const last = normalized.data[normalized.data.length - 1]?.time;
    nodes.title.textContent = options.title || endpoint;
    nodes.source.textContent = options.source || "Endpoint openfindata";
    if (nodes.extracted) {
      nodes.extracted.textContent = extractionTimestamp();
    }
    if (nodes.cutoff) nodes.cutoff.textContent = `${first} → ${last}`;
    if (nodes.sourceNote) {
      nodes.sourceNote.innerHTML = `<strong>Fontes dos dados.</strong> Fonte primária/curadoria: <a href="https://github.com/robertoecf/openfindata">${PRIMARY_SOURCE}</a>. Subsets originais: ${options.source || "endpoint openfindata"}.`;
    }
    const auditUrl = new URL(endpoint, window.location.origin);
    const auditPath = `${auditUrl.pathname}${auditUrl.search}`;
    const auditLink = document.createElement("a");
    auditLink.href = auditPath;
    auditLink.textContent = "JSON auditável";
    nodes.summary.replaceChildren(
      auditLink,
      document.createTextNode(
        ` · Script: ${CHART_SCRIPT} · Renderer: ${CHART_RENDERER} · Frequência: ${options.frequency || "não inferida"} · ${normalized.data.length} pontos · ${first} a ${last} · data=${normalized.dateKey} · valor=${normalized.valueKey || "OHLC"}`,
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

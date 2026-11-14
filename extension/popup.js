const DEFAULT_ENDPOINT = "https://the4thlover.tech";
const BUILTIN_ORIGINS = new Set([
  "https://the4thlover.tech",
  "http://localhost",
  "http://127.0.0.1",
]);

const STAGE_LABELS = {
  extract: "Extract document",
  understand: "Extract claims & queries",
  retrieve: "Retrieve live coverage",
  story: "Match same-event peers",
  signals_single: "Single-actor signals",
  signals_coordinated: "Coordination signals",
  score: "Calibrated combiner",
  explain: "Evidence summary",
};

const state = {
  endpoint: DEFAULT_ENDPOINT,
  mode: "url",
  tabUrl: "",
  tabTitle: "",
  tabDomain: "",
  selectionText: "",
  domText: "",
  eventSource: null,
  activeAnalysisId: null,
};

const el = {
  brandLink: document.getElementById("brand-link"),
  healthPill: document.getElementById("health-pill"),
  healthDot: document.getElementById("health-dot"),
  healthLabel: document.getElementById("health-label"),
  sidepanelBtn: document.getElementById("sidepanel-btn"),
  settingsPanel: document.getElementById("settings-panel"),
  settingsForm: document.getElementById("settings-form"),
  endpointInput: document.getElementById("endpoint-input"),
  tabUrlBtn: document.getElementById("tab-url"),
  tabSelectionBtn: document.getElementById("tab-selection"),
  tabDomBtn: document.getElementById("tab-dom"),
  selectionBadge: document.getElementById("selection-badge"),
  previewDomain: document.getElementById("preview-domain"),
  previewTitle: document.getElementById("preview-title"),
  payloadInput: document.getElementById("payload-input"),
  langSelect: document.getElementById("lang-select"),
  openSiteBtn: document.getElementById("open-site-btn"),
  analyzeBtn: document.getElementById("analyze-btn"),
  errorBox: document.getElementById("error-box"),
  progressCard: document.getElementById("progress-card"),
  progressStatus: document.getElementById("progress-status"),
  liveReportLink: document.getElementById("live-report-link"),
  stageList: document.getElementById("stage-list"),
  resultCard: document.getElementById("result-card"),
  scoreSingle: document.getElementById("score-single"),
  scoreCoordinated: document.getElementById("score-coordinated"),
  summaryBox: document.getElementById("summary-box"),
  contextCounts: document.getElementById("context-counts"),
  summaryText: document.getElementById("summary-text"),
  reasonsList: document.getElementById("reasons-list"),
  fullReportBtn: document.getElementById("full-report-btn"),
};

function normalizeEndpoint(raw) {
  const trimmed = (raw || "").trim().replace(/\/+$/, "");
  if (!trimmed) return DEFAULT_ENDPOINT;
  const parsed = new URL(trimmed);
  return `${parsed.protocol}//${parsed.host}`;
}

function cleanDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./i, "");
  } catch {
    return "";
  }
}

function wordCount(text) {
  const trimmed = (text || "").trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

function setError(message) {
  if (!message) {
    el.errorBox.hidden = true;
    el.errorBox.textContent = "";
    return;
  }
  el.errorBox.textContent = message;
  el.errorBox.hidden = false;
}

const hasChromeStorage = typeof chrome !== "undefined" && Boolean(chrome.storage && chrome.storage.local);

async function readPrefs(keys) {
  if (hasChromeStorage) return chrome.storage.local.get(keys);
  const out = {};
  for (const k of keys) {
    try {
      const val = window.localStorage.getItem(`dtn_${k}`);
      if (val !== null) out[k] = val;
    } catch {
      // Ignore storage restrictions
    }
  }
  return out;
}

async function writePrefs(obj) {
  if (hasChromeStorage) {
    await chrome.storage.local.set(obj);
    return;
  }
  for (const [k, v] of Object.entries(obj)) {
    try {
      window.localStorage.setItem(`dtn_${k}`, String(v));
    } catch {
      // Ignore
    }
  }
}

async function loadSettings() {
  const stored = await readPrefs(["endpoint", "lang"]);
  if (typeof stored.endpoint === "string" && stored.endpoint.trim()) {
    try {
      state.endpoint = normalizeEndpoint(stored.endpoint);
    } catch {
      state.endpoint = DEFAULT_ENDPOINT;
    }
  }
  if (typeof stored.lang === "string") {
    el.langSelect.value = stored.lang;
  }
  el.endpointInput.value = state.endpoint;
  el.brandLink.href = state.endpoint;
}

async function checkHealth() {
  el.healthDot.className = "status-dot";
  el.healthLabel.textContent = cleanDomain(state.endpoint) || "server";
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    const res = await fetch(`${state.endpoint}/api/health`, {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    el.healthDot.className = data.status === "ok" ? "status-dot online" : "status-dot offline";
    const ver = typeof data.pipeline_version === "string" ? data.pipeline_version.slice(0, 9) : "ok";
    el.healthLabel.textContent = `${cleanDomain(state.endpoint)} · ${ver}`;
  } catch {
    el.healthDot.className = "status-dot offline";
    el.healthLabel.textContent = `${cleanDomain(state.endpoint)} · offline`;
  }
}

async function ensureHostPermission(endpoint) {
  const parsed = new URL(endpoint);
  const baseOrigin = `${parsed.protocol}//${parsed.hostname}`;
  if (BUILTIN_ORIGINS.has(baseOrigin)) return true;
  if (typeof chrome === "undefined" || !chrome.permissions) return true;
  const pattern = `${parsed.origin}/*`;
  const already = await chrome.permissions.contains({ origins: [pattern] });
  if (already) return true;
  return chrome.permissions.request({ origins: [pattern] });
}

function captureFromPageDom() {
  const selection = (window.getSelection ? window.getSelection().toString() : "").trim();
  const root =
    document.querySelector("article") ||
    document.querySelector('[role="main"]') ||
    document.querySelector("main") ||
    document.body;
  const seen = new Set();
  const paragraphs = [];
  if (root) {
    const nodes = root.querySelectorAll("h1, h2, p, blockquote, li");
    for (const node of nodes) {
      const text = (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
      if (text.length < 35 || seen.has(text)) continue;
      seen.add(text);
      paragraphs.push(text);
      if (paragraphs.join("\n\n").length >= 12000) break;
    }
  }
  const domText = paragraphs.join("\n\n").slice(0, 12000);
  return { selection: selection.slice(0, 12000), domText };
}

async function inspectActiveTab() {
  if (typeof chrome === "undefined" || !chrome.tabs || !chrome.tabs.query) {
    el.previewDomain.textContent = "Standalone preview";
    el.previewTitle.textContent = "Paste any article link or text below";
    return;
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) {
    el.previewDomain.textContent = "No active tab";
    el.previewTitle.textContent = "Paste any link or text below";
    return;
  }

  const url = tab.url || "";
  const isHttp = /^https?:\/\//i.test(url);
  state.tabUrl = isHttp ? url : "";
  state.tabTitle = tab.title || url || "Current tab";
  state.tabDomain = isHttp ? cleanDomain(url) : "Browser page";

  el.previewDomain.textContent = state.tabDomain || "Current tab";
  el.previewTitle.textContent = state.tabTitle;

  if (isHttp && tab.id !== undefined) {
    try {
      const [injection] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: captureFromPageDom,
      });
      if (injection && injection.result) {
        state.selectionText = injection.result.selection || "";
        state.domText = injection.result.domText || "";
      }
    } catch {
      // Restricted pages (Chrome Web Store, sandboxed frames) disallow script injection.
    }
  }

  if (state.selectionText) {
    el.selectionBadge.textContent = `${wordCount(state.selectionText)}w`;
    el.selectionBadge.hidden = false;
    applyMode("selection");
  } else if (state.tabUrl) {
    applyMode("url");
  } else {
    applyMode("dom");
  }
}

function applyMode(mode) {
  state.mode = mode;
  for (const [id, btn] of [
    ["url", el.tabUrlBtn],
    ["selection", el.tabSelectionBtn],
    ["dom", el.tabDomBtn],
  ]) {
    btn.classList.toggle("active", id === mode);
  }

  if (mode === "url") {
    el.payloadInput.value = state.tabUrl;
    el.payloadInput.placeholder = "https://example.com/article…";
  } else if (mode === "selection") {
    el.payloadInput.value = state.selectionText;
    el.payloadInput.placeholder = "Highlight a claim or paragraph on the page, or paste text…";
  } else {
    const titlePrefix = state.tabTitle ? `${state.tabTitle}\n\n` : "";
    el.payloadInput.value = state.domText ? `${titlePrefix}${state.domText}`.slice(0, 12000) : "";
    el.payloadInput.placeholder = "Visible article text extracted from this tab (works on social & subscriber feeds)…";
  }
  setError(null);
}

function resolveInput() {
  const value = el.payloadInput.value.trim();
  if (!value) {
    throw new Error("Select a tab link, highlight text, or paste content first.");
  }
  const isSingleUrl = /^https?:\/\/\S+$/i.test(value) && !value.includes("\n");
  const kind = state.mode === "url" && isSingleUrl ? "url" : isSingleUrl ? "url" : "text";
  if (state.mode === "url" && kind !== "url") {
    throw new Error("Enter a valid http(s) URL, or switch to Selection / Reader text.");
  }
  return {
    kind,
    value,
    explanation_language: el.langSelect.value || null,
  };
}

function buildDeepLink(autorun) {
  const payload = resolveInput();
  const params = new URLSearchParams();
  params.set(payload.kind === "url" ? "url" : "text", payload.value.slice(0, 8000));
  if (payload.explanation_language) params.set("lang", payload.explanation_language);
  if (autorun) params.set("autorun", "1");
  return `${state.endpoint}/?${params.toString()}`;
}

function renderStages(steps) {
  el.stageList.replaceChildren();
  for (const step of steps || []) {
    const li = document.createElement("li");
    li.className = "stage-row";

    const left = document.createElement("div");
    left.className = "stage-left";

    const dot = document.createElement("span");
    dot.className = `stage-dot ${step.state}`;

    const name = document.createElement("span");
    name.className = "stage-name";
    name.textContent = STAGE_LABELS[step.name] || step.name;

    left.append(dot, name);

    const detail = document.createElement("span");
    detail.className = "stage-detail";
    detail.textContent = step.error || step.detail || (step.duration_ms != null ? `${(step.duration_ms / 1000).toFixed(1)}s` : step.state);

    li.append(left, detail);
    el.stageList.appendChild(li);
  }
}

function renderDimensionBox(target, label, kindClass, dimScore) {
  target.replaceChildren();

  const header = document.createElement("div");
  header.className = "score-dim";
  header.textContent = label;
  target.appendChild(header);

  if (!dimScore || dimScore.abstain_reason || dimScore.confidence == null) {
    const abstain = document.createElement("div");
    abstain.className = "score-abstain";
    abstain.textContent = "Not enough evidence";
    const reason = document.createElement("p");
    reason.className = "score-sub";
    reason.textContent = (dimScore && dimScore.abstain_reason) || "Insufficient peer coverage to compare.";
    target.append(abstain, reason);
    return;
  }

  const pct = Math.round(dimScore.confidence * 100);
  const num = document.createElement("div");
  num.className = `score-num ${kindClass}`;
  num.textContent = `${pct}%`;

  const meter = document.createElement("div");
  meter.className = "meter";
  const fill = document.createElement("div");
  fill.className = `meter-fill ${kindClass}`;
  fill.style.width = `${Math.max(3, Math.min(100, pct))}%`;
  meter.appendChild(fill);

  const activeContributors = (dimScore.breakdown || [])
    .filter((b) => Math.abs(b.contribution) >= 0.05)
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, 2)
    .map((b) => `${b.family.replace(/_/g, " ")} (${b.contribution >= 0 ? "+" : ""}${b.contribution.toFixed(2)})`);

  const sub = document.createElement("p");
  sub.className = "score-sub";
  sub.textContent = activeContributors.length
    ? activeContributors.join(" · ")
    : "No manipulation signals fired across checked coverage.";

  target.append(num, meter, sub);
}

function renderAnalysis(analysis) {
  const reportUrl = `${state.endpoint}/analyses/${encodeURIComponent(analysis.id)}`;
  el.liveReportLink.href = reportUrl;
  el.fullReportBtn.href = reportUrl;

  if (analysis.steps && analysis.steps.length) {
    renderStages(analysis.steps);
  }

  if (analysis.status === "failed") {
    el.progressCard.hidden = false;
    el.progressStatus.textContent = "Analysis could not complete";
    setError(analysis.error || "A pipeline stage failed. Try Reader text mode if the page blocked fetching.");
    el.analyzeBtn.disabled = false;
    el.analyzeBtn.textContent = "Check story";
    return;
  }

  if (analysis.scores) {
    el.resultCard.hidden = false;
    renderDimensionBox(el.scoreSingle, "Single-actor signs", "single", analysis.scores.single);
    renderDimensionBox(el.scoreCoordinated, "Coordinated signs", "coordinated", analysis.scores.coordinated);
  }

  const contextItems = analysis.context || [];
  const factChecks = contextItems.filter((c) => c.fact_check != null).length;
  const peers = contextItems.filter((c) => c.in_story && c.fact_check == null).length;

  if (analysis.explanation || contextItems.length > 0) {
    el.summaryBox.hidden = false;
    el.contextCounts.textContent = `${peers} peer${peers === 1 ? "" : "s"} · ${factChecks} fact-check${factChecks === 1 ? "" : "s"}`;
    el.summaryText.textContent =
      (analysis.explanation && analysis.explanation.summary) ||
      (analysis.topic && analysis.topic.summary) ||
      "";
    el.reasonsList.replaceChildren();
    for (const r of (analysis.explanation && analysis.explanation.reasons) || []) {
      const li = document.createElement("li");
      li.textContent = r.text;
      el.reasonsList.appendChild(li);
    }
  }

  if (analysis.status === "done") {
    el.progressStatus.textContent = "Completed";
    el.analyzeBtn.disabled = false;
    el.analyzeBtn.textContent = "Check story";
  }
}

function closeStream() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
}

async function fetchSnapshot(id) {
  const res = await fetch(`${state.endpoint}/api/analyses/${encodeURIComponent(id)}`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function streamAnalysis(id) {
  closeStream();
  state.activeAnalysisId = id;
  let settled = false;

  const connect = () => {
    if (settled || state.activeAnalysisId !== id) return;
    const es = new EventSource(`${state.endpoint}/api/analyses/${encodeURIComponent(id)}/events`);
    state.eventSource = es;

    es.addEventListener("snapshot", (ev) => {
      try {
        const { analysis } = JSON.parse(ev.data);
        renderAnalysis(analysis);
        if (analysis.status === "done" || analysis.status === "failed") {
          settled = true;
          closeStream();
        }
      } catch {
        // Ignore malformed frame
      }
    });

    es.addEventListener("queue", (ev) => {
      try {
        const { position } = JSON.parse(ev.data);
        el.progressStatus.textContent = `Queued (position ${position})…`;
      } catch {
        // Ignore
      }
    });

    es.addEventListener("step", (ev) => {
      try {
        const { step } = JSON.parse(ev.data);
        el.progressStatus.textContent = `${STAGE_LABELS[step.name] || step.name}…`;
        fetchSnapshot(id)
          .then((record) => {
            if (state.activeAnalysisId === id) renderAnalysis(record);
          })
          .catch(() => {});
      } catch {
        // Ignore
      }
    });

    es.addEventListener("done", (ev) => {
      settled = true;
      closeStream();
      try {
        const { analysis } = JSON.parse(ev.data);
        renderAnalysis(analysis);
      } catch {
        // Ignore
      }
    });

    es.onerror = () => {
      if (settled || state.activeAnalysisId !== id) return;
      closeStream();
      fetchSnapshot(id)
        .then((record) => {
          if (state.activeAnalysisId !== id) return;
          renderAnalysis(record);
          if (record.status === "done" || record.status === "failed") {
            settled = true;
          } else {
            setTimeout(connect, 900);
          }
        })
        .catch(() => {
          setError("Lost connection to the analysis stream. Click Live view to continue in tab.");
          el.analyzeBtn.disabled = false;
          el.analyzeBtn.textContent = "Check story";
        });
    };
  };

  connect();
}

async function startAnalysis() {
  setError(null);
  let input;
  try {
    input = resolveInput();
  } catch (err) {
    setError(err.message);
    return;
  }

  el.analyzeBtn.disabled = true;
  el.analyzeBtn.textContent = "Checking…";
  el.resultCard.hidden = true;
  el.summaryBox.hidden = true;
  el.progressCard.hidden = false;
  el.progressStatus.textContent = "Submitting…";
  el.stageList.replaceChildren();

  try {
    await writePrefs({ lang: el.langSelect.value });
    const res = await fetch(`${state.endpoint}/api/analyses`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(input),
    });

    if (!res.ok) {
      let msg = `Request failed (${res.status})`;
      try {
        const errBody = await res.json();
        if (errBody && errBody.message) msg = errBody.message;
      } catch {
        // Non-JSON error
      }
      throw new Error(msg);
    }

    const created = await res.json();
    el.liveReportLink.href = `${state.endpoint}/analyses/${encodeURIComponent(created.id)}`;
    streamAnalysis(created.id);
  } catch (err) {
    el.progressCard.hidden = true;
    el.analyzeBtn.disabled = false;
    el.analyzeBtn.textContent = "Check story";
    setError(err instanceof Error ? err.message : "Could not reach the connected server.");
  }
}

el.healthPill.addEventListener("click", () => {
  el.settingsPanel.hidden = !el.settingsPanel.hidden;
});

for (const chip of document.querySelectorAll(".chip[data-endpoint]")) {
  chip.addEventListener("click", () => {
    el.endpointInput.value = chip.dataset.endpoint || DEFAULT_ENDPOINT;
  });
}

el.settingsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const normalized = normalizeEndpoint(el.endpointInput.value);
    const granted = await ensureHostPermission(normalized);
    if (!granted) {
      setError("Host permission was declined for that server.");
      return;
    }
    state.endpoint = normalized;
    el.endpointInput.value = normalized;
    el.brandLink.href = normalized;
    await writePrefs({ endpoint: normalized });
    el.settingsPanel.hidden = true;
    await checkHealth();
  } catch {
    setError("Enter a valid http:// or https:// server URL.");
  }
});

el.sidepanelBtn.addEventListener("click", async () => {
  if (typeof chrome === "undefined" || !chrome.sidePanel || !chrome.sidePanel.open) return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.windowId !== undefined) {
    await chrome.sidePanel.open({ windowId: tab.windowId });
    window.close();
  }
});

for (const btn of [el.tabUrlBtn, el.tabSelectionBtn, el.tabDomBtn]) {
  btn.addEventListener("click", () => applyMode(btn.dataset.mode));
}

el.openSiteBtn.addEventListener("click", async () => {
  try {
    const targetUrl = buildDeepLink(true);
    if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.create) {
      await chrome.tabs.create({ url: targetUrl });
    } else {
      window.open(targetUrl, "_blank", "noopener");
    }
  } catch (err) {
    setError(err.message);
  }
});

el.analyzeBtn.addEventListener("click", () => {
  void startAnalysis();
});

document.addEventListener("DOMContentLoaded", async () => {
  await loadSettings();
  void checkHealth();
  await inspectActiveTab();
});

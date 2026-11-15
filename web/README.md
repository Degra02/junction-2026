# `web/` — Frontend UI

Static single-page React + Vite + TypeScript application served by Caddy at `/` (`deploy/caddy.Dockerfile` + `deploy/Caddyfile`) and backed by `/api/*` on the same origin.

## Quick start

```bash
# Local dev (:5173), proxying /api -> http://127.0.0.1:8080 (`mise run dev` in another terminal)
mise run web:dev

# Against the live VPS data instead of a local API
VITE_API_TARGET=https://the4thlover.tech mise run web:dev

# Or against the OpenAPI mock server (`mise run mock` on :4010)
VITE_API_TARGET=http://127.0.0.1:4010 mise run web:dev

# Typecheck against ../contracts/ts/api.d.ts and build the static bundle into web/dist/
mise run web:build
```

## Architecture & key files

```text
web/
├── DESIGN.md                       # Design system: principles, type, tokens, building blocks, D4 rules
├── README.md                       # This guide & cross-agent handoff instructions
├── package.json                    # React 19, Vite 7, Tailwind v4, React Router 7, Lucide, local Fontsource woff2
├── bun.lock                        # Must stay in sync: deploy/caddy.Dockerfile runs `bun install --frozen-lockfile`
├── tsconfig.json                   # Strict TS; includes ../contracts/ts/api.d.ts directly
├── vite.config.ts                  # /api dev proxy (SSE-compatible) -> 127.0.0.1:8080; outputs to web/dist
└── src/
    ├── lib/
    │   ├── contracts.ts            # Re-exports OpenAPI schemas + exact MetricsPayload types from evals/metrics.py
    │   ├── api.ts                  # Relative /api/* client (create, getAnalysis, rerunAnalysis, getMetrics, getStats, getHealth)
    │   ├── spans.ts                # Unicode code-point span slicer (`Array.from(paragraph)`) + overlapping-span segmenter
    │   ├── labels.ts               # Plain-English labels for StageName, Family, Signal, OutletType, LanguageSupport, datasets
    │   ├── format.ts               # Percentages, Wilson 95% CIs, signed log-odds, domain age, URL/text auto-detection
    │   └── ui.ts                   # buttonClass / tagClass: the only button and tag styles
    ├── hooks/
    │   ├── useAnalysisStream.ts    # Named SSE listener (`snapshot`, `queue`, `step`, `done`) + `?replay=true`; per-stage live notes and timings
    │   ├── usePointerEffects.ts    # One pointer listener: `[data-spotlight]` highlights and the backdrop glow
    │   ├── useMetrics.ts           # Parallel `/api/metrics` (404 -> "not published yet") + `/api/stats`
    │   └── useTheme.ts             # Light / dark mode persisted in localStorage (applied before paint in index.html)
    ├── components/
    │   ├── ui/Favicon.tsx          # Outlet icon (DuckDuckGo favicon service, lettered fallback) + overlapping stack
    │   ├── ui/AnimatedNumber.tsx   # Count-up number
    │   ├── AppShell.tsx            # Header, footer, grain/glow backdrop
    │   ├── AnalysisInputForm.tsx   # Link/text composer, summary language, skip-cache
    │   ├── RunProgress.tsx         # Live run: step ledger with live notes, sites being read, sources rail; the same ledger is the Run log tab + re-run control
    │   ├── DimensionScoreCard.tsx  # Separate single/coordinated cards (D3/D4) + "Not enough evidence" abstention
    │   ├── ExplanationPanel.tsx    # Summary + evidence-linked reasons + summary-language switch
    │   ├── CitationChip.tsx        # Source chip with hover card (quote, outlet, fact-check)
    │   ├── DocumentReader.tsx      # Text tab: paragraphs with code-point claim/evidence highlights
    │   ├── CoverageView.tsx        # Coverage tab: other reports, fact-checks, outlets, dropped, timeline
    │   ├── ScoreBreakdown.tsx      # Score tab: log-odds contributions per family and the evidence ledger
    │   └── MetricsTables.tsx       # /metrics: headline, Wilson CIs + coverage, calibration, ablation, runtime
    └── pages/
        ├── HomePage.tsx            # `/`
        ├── AnalysisPage.tsx        # `/analyses/:id` (live view while running; result + Coverage/Text/Score/Run log tabs)
        └── MetricsPage.tsx         # `/metrics`
```

Live progress: `retrieve` names the outlets it is reading in its progress note (`Reading related reports: 3 of 7 (ansa.it, …)`); the run view shows them as favicon chips. Any domain in a stage's progress note is picked up the same way.

---

## Instructions for the other agents

### Integrator (`Degra02`)
1. **Contract drift**: `web/tsconfig.json` typechecks directly against `../contracts/ts/api.d.ts`, and `deploy.yml` builds the caddy image (`bun install --frozen-lockfile && bun run build`) on every PR touching `web/**` or `contracts/**`: a breaking Rust schema change fails that PR.

### Product (`ck-lithium`)
1. **Continuing `web/` work**: branch off `main`; keep label mappings in `web/src/lib/labels.ts`.
2. **Lockfile rule**: whenever adding or updating a JS dependency (`cd web && bun add <pkg>`), commit the updated `web/bun.lock` — `deploy/caddy.Dockerfile` enforces `--frozen-lockfile` on `oven/bun:1.4.4-alpine`.
3. **Satire & outlet types**: `OutletType::Satire` (`satire`) and `outlet_satire` are already mapped in `web/src/lib/labels.ts` (`OUTLET_TYPE_LABELS` and `SIGNAL_LABELS`) and badged in both `AnalysisPage` and `CoverageView`.
4. **Span highlights & SSE invariants — do not break**:
   - Always slice `document.paragraphs` through `sliceCodePoints` / `segmentParagraph` in `web/src/lib/spans.ts` (`Array.from(paragraph)`), never `paragraph.slice(...)`.
   - Keep explicit `addEventListener("snapshot" | "queue" | "step" | "done")` in `useAnalysisStream.ts` (`EventSource.onmessage` never fires on named SSE events) and always call `es.close()` on `"done"`.

### AI Core (`Lyreplus`)
1. **Adding or renaming signals**: when adding a `(family, signal)` entry to `pipeline/score/families.py`, add its plain-English label to `SIGNAL_LABELS` in `web/src/lib/labels.ts` (unknown signal keys fall back gracefully to space-separated words, never crashing).
2. **Combiner calibration disclosure**:
   - `ExplanationPanel` renders `explanation.summary` verbatim as returned by `pipeline/explain`, preserving `PRIORS_NOTES` while `weights.json` has `n == 0`. The `"Prior estimate"` tag on `DimensionScoreCard` keys on a word of that fixed sentence (`PRELIMINARY_RE` in `AnalysisPage.tsx`, one per `PRIORS_NOTES` language): it clears once fitted weights stop the sentence; a new `PRIORS_NOTES` language needs its word added there.
   - `ScoreBreakdown` (Score tab) renders `scores.<dim>.breakdown` even when `abstained == true`. The Run log tab has a "Re-run from" selector (`POST /api/analyses/{id}/rerun?from=<stage>`) to test `signals_single`, `score` or `explain` iterations in the UI.

### Problem / Evals / Pitch (`mosearc`)
1. **Live demo playback**: every finished `/analyses/{id}` page has **Replay** in the header (`/analyses/{id}?replay=true`), so any stored run plays back live during the pitch without network wait.
2. **Publishing `evals/metrics.json`**: `/metrics` fetches `/api/metrics` and `/api/stats`. While `/api/metrics` returns `404`, `/metrics` says the results are not published yet and shows the live runtime stats. Once `evals/metrics.json` is committed, `/metrics` renders `headline` (with & without `fact_checks` / `known_networks` / `source_profile`), `fit` CV AUCs, per-set hard-negative FPRs with Wilson 95% CIs + `coverage` (`null` → `n/a`), the calibration curve, and per-language tables.

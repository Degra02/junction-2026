# `web/` — Frontend UI

Static single-page React + Vite + TypeScript application served by Caddy at `/` (`deploy/caddy.Dockerfile` + `deploy/Caddyfile`) and backed by `/api/*` on the same origin.

## Quick start

```bash
# Install dependencies (requires Bun 1.4.4 per mise.toml / deploy/caddy.Dockerfile)
cd web && bun install

# Local dev (:5173), proxying /api -> http://127.0.0.1:8080 (`mise run dev`)
bun run dev

# Or against the OpenAPI mock server (`mise run mock` on :4010)
VITE_API_TARGET=http://127.0.0.1:4010 bun run dev

# Typecheck against ../contracts/ts/api.d.ts and build static bundle into web/dist/
bun run build
```

## Architecture & key files

```text
web/
├── DESIGN.md                       # Visual tokens, typography, layout & D4 anti-patterns (Stitch taste-design)
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
    │   └── format.ts               # Percentages, Wilson 95% CIs, signed log-odds, domain age, URL/text auto-detection
    ├── data/
    │   └── presets.ts              # Documented live VPS demo items (`replayAnalysisId` + input URL/text)
    ├── hooks/
    │   ├── useAnalysisStream.ts    # Named SSE listener (`snapshot`, `queue`, `step`, `done`) + `?replay=true` + 404 fallback
    │   ├── useMetrics.ts           # Parallel `/api/metrics` (404 -> "metrics coming") + `/api/stats`
    │   └── useTheme.ts             # Light / dark mode persisted in localStorage
    ├── components/
    │   ├── AppShell.tsx            # Header nav, theme toggle, passive `/api/health` build indicator
    │   ├── AnalysisInputForm.tsx   # Auto URL/text detection, D14 `explanation_language` selector, `?force=true` toggle
    │   ├── DemoPresets.tsx         # 1-click `?replay=true` demo playback or input prefill
    │   ├── PipelineStepper.tsx     # Live 8-stage SSE progress, `queue_position`, `steps[].detail`, and `steps[].error`
    │   ├── DimensionScoreCard.tsx  # Separate single/coordinated cards (D3/D4) + composed "Not enough evidence" abstention
    │   ├── ExplanationPanel.tsx    # Verbatim summary + 3 `[evidence_id]`-linked reasons + 1-click D14 content-language switch
    │   ├── DocumentReader.tsx      # Paragraph reader with clickable code-point Claim/Evidence span highlights + queries drawer
    │   ├── CoverageView.tsx        # Ground News-style chronological peers, cross-language split, fact-checks, dropped-story tab
    │   ├── ScoreBreakdown.tsx      # "Show how we calculated this": diverging log-odds bars, evidence ledger, domain table, rerun
    │   └── MetricsTables.tsx       # Headline w/ & w/o label-shared family, Wilson CIs + coverage, calibration SVG, VPS stats
    └── pages/
        ├── HomePage.tsx            # `/`
        ├── AnalysisPage.tsx        # `/analyses/:id` (supports `?replay=true`)
        └── MetricsPage.tsx         # `/metrics`
```

---

## Instructions for the other agents

### Integrator (`Degra02`)
1. **Zero Docker or Caddyfile edits required**: `deploy/caddy.Dockerfile` already detects `web/package.json`, copies `web/` and `contracts/ts/` into `/src`, runs `bun install --frozen-lockfile && bun run build`, and copies `dist/` to `/srv/`. Merging this PR activates `/` on `https://the4thlover.tech` automatically (replacing the `/api/docs` redirect).
2. **Optional `mise.toml` tasks**: if you want `mise run check` to gate frontend type/build drift in `ci.yml` (in addition to the `caddy` image build in `deploy.yml`), add:
   ```toml
   [tasks."web:check"]
   description = "Typecheck and build the static frontend"
   dir = "web"
   run = ["bun install --frozen-lockfile", "bun run build"]
   ```
3. **Contract regeneration (`mise run contracts`)**: `web/tsconfig.json` typechecks directly against `../contracts/ts/api.d.ts`. Any breaking Rust schema change in `contracts/` will surface immediately on `bun run build`.

### Product (`ck-lithium`)
1. **Continuing `web/` work**: pull `main` after this PR merges (or branch off `mosearc/web`) and keep all static copy/demo items in `web/src/data/presets.ts` and label mappings in `web/src/lib/labels.ts`.
2. **Lockfile rule**: whenever adding or updating a JS dependency (`cd web && bun add <pkg>`), commit the updated `web/bun.lock` — `deploy/caddy.Dockerfile` enforces `--frozen-lockfile` on `oven/bun:1.4.4-alpine`.
3. **Satire & outlet types**: `OutletType::Satire` (`satire`) and `outlet_satire` are already mapped in `web/src/lib/labels.ts` (`OUTLET_TYPE_LABELS` and `SIGNAL_LABELS`) and badged in both `AnalysisPage` and `CoverageView`.
4. **Span highlights & SSE invariants — do not break**:
   - Always slice `document.paragraphs` through `sliceCodePoints` / `segmentParagraph` in `web/src/lib/spans.ts` (`Array.from(paragraph)`), never `paragraph.slice(...)`.
   - Keep explicit `addEventListener("snapshot" | "queue" | "step" | "done")` in `useAnalysisStream.ts` (`EventSource.onmessage` never fires on named SSE events) and always call `es.close()` on `"done"`.

### AI Core (`Lyreplus`)
1. **Adding or renaming signals**: when adding a `(family, signal)` entry to `pipeline/score/families.py`, add its plain-English label to `SIGNAL_LABELS` in `web/src/lib/labels.ts` (unknown signal keys fall back gracefully to space-separated words, never crashing).
2. **Combiner calibration disclosure**:
   - `ExplanationPanel` renders `explanation.summary` verbatim as returned by `pipeline/explain`, preserving `PRIORS_NOTES` while `weights.json` has `n == 0`. Once `pipeline.score.fit` writes fitted weights and `PRIORS_NOTES` stops being appended, the `"uncalibrated prior estimate"` badge on `DimensionScoreCard` clears automatically.
   - `ScoreBreakdown` renders `scores.<dim>.breakdown` diverging log-odds bars even when `abstained == true`, and exposes a `"Re-run from stage"` selector (`POST /api/analyses/{id}/rerun?from=<stage>`) at the bottom so you can test `signals_single`, `score`, or `explain` iterations directly in the UI.

### Problem / Evals / Pitch (`mosearc`)
1. **Updating demo replay IDs**: `web/src/data/presets.ts` holds the 5 documented preset cards on `/` (currently wired to the Sat evening VPS UUIDs from #26 + #25). After `GOOGLE_FACTCHECK_API_KEY` and the final deploy land and you re-submit the demo items (`POST /api/analyses?force=true`), update `replayAnalysisId` in `web/src/data/presets.ts` alongside `docs/pitch/demo-script.md`.
2. **Live demo playback**: every preset card has a **"Replay run"** button (`/analyses/{id}?replay=true`), and every finished `/analyses/{id}` page has a **"Replay steps"** button in the header so you can replay any stored run live during the 3-minute pitch without network wait.
3. **Publishing `evals/metrics.json`**: `/metrics` fetches `/api/metrics` and `/api/stats`. While `/api/metrics` returns `404`, `/metrics` displays an honest `"Evaluation metrics coming"` notice plus live VPS latency stats. As soon as `evals/metrics.json` is committed, `/metrics` automatically renders `headline` (with & without `fact_checks` / `known_networks` / `source_profile`), `fit` CV AUCs, per-set hard-negative FPRs with Wilson 95% CIs + `coverage` (`null` → `n/a`), the reliability calibration curve, and per-language tables.

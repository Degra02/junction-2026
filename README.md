# The4thLover — Decode the Noise (Junction 2026)

Live at **<https://the4thlover.tech>** · [Benchmarks (`/metrics`)](https://the4thlover.tech/metrics) · [Live Source Graph (`/sources`)](https://the4thlover.tech/sources) · [Browser Extension (`/extension`)](https://the4thlover.tech/extension) · [OpenAPI (`/api/docs`)](https://the4thlover.tech/api/docs)

Paste an article URL, text, or meme in any language. **The4thLover** retrieves how independent outlets and fact-checkers covered the same event, checks domain provenance and shared tracking infrastructure, and computes calibrated signal confidences for **content-level manipulation** and **coordinated amplification** — showing the full log-odds calculation, verbatim-checked quotes, and clickable source links rather than an unverifiable binary label.

## Challenges & Partner Integrations

| Challenge | How it is used in The4thLover |
|---|---|
| **Hostinger — Decode the Noise** *(Agentic AI Track)* | Deployed live on a single **Hostinger KVM 2 VPS** (2 vCPU, 8 GB RAM, no GPU) behind Caddy TLS (`deploy/`): Rust (`axum`) API + SQLite, Python FastAPI worker running CPU models, and LLM calls routed via **Hostinger AI Router** (`https://router.hostinger.com/v1`). Tackles *Name the technique*, *Trust the source*, and *Spot the swarm*, with published precision, Wilson 95% CIs, and per-hard-negative false-positive rates (`/metrics`). |
| **Oxylabs — Best agentic usecase of Oxylabs Web API** | Runtime web verification (`OXYLABS_TOKEN` via `https://api-aistudio.oxylabs.io`):<br>• **`POST /search/instant`** (`pipeline/retrieve/oxylabs.py`, `pipeline/retrieve/social.py`): exact-phrase search to uncover copied passages across websites and X/Reddit accounts, multilingual news coverage beyond RSS feeds, and site-scoped ClaimReview fact-check search.<br>• **`POST /scrape`** (`pipeline/extract/scraper.py`): clean Markdown/text extraction on bot-challenged or JS-gated pages (e.g. France24, TASS) with zero headless browser overhead.<br>Every claim, copy, and reason links directly to its retrieved source URL. |
| **Google DeepMind — Best Use of Gemini API** | Four bounded stages where Gemini never sets raw scores and every quotation is verified verbatim by Rust code-point span checks (`contracts/src/apply.rs`, `pipeline/common/spans.py`):<br>• **Multimodal meme/screenshot vision** (`pipeline/extract/vision.py`, `generateContent`): OCR, neutral `[Visual context]`, satire-meme guard, and implied visual argument extraction.<br>• **Multimodal `rhetoric` rater** (`pipeline/signals/rhetoric.py`): inspects text + image together for SemEval-2023 persuasion categories, dropping quoted-speech hits and non-verbatim spans.<br>• **Selective NLI cascade** (`pipeline/signals/judge.py`) + **structured multilingual `understand` & `explain`** (`gemini-3.1-flash-lite` / `gemini-4-hydrogen`). |
| **OpenAI — Best Use of Codex** | Engineered for 4-person parallel agent development across 70+ PRs in 48 hours (`AGENTS.md`, `DECISIONS.md`, `docs/next-steps.md`): Rust types in `contracts/` serve as single source of truth (`mise run contracts` generates `openapi.json`, Pydantic `contracts.py`, and TypeScript `api.d.ts`), each stage tests in isolation against `contracts/fixtures/analysis.json`, and CI enforces `mise run check` (`55` Rust nextest + `524` Python pytest tests, `clippy -D warnings`, `ruff`, contract-drift check, and `gitleaks`). |

## Quickstart
```sh
mise trust && mise run setup   # pinned node/python/bun/uv/rust/nextest/gitleaks, git hooks, uv sync
cp .env.example .env           # fill API keys (LLM_*, OXYLABS_TOKEN, GEMINI_API_KEY, GOOGLE_FACTCHECK_API_KEY)
mise run check                 # what CI runs (gitleaks, rustfmt, clippy, nextest, ruff, pytest, contract drift)
mise run dev                   # worker :8001 + API :8080, docs at http://127.0.0.1:8080/api/docs
mise run web:dev               # Vite UI on :5173 proxying /api to :8080
```

## Layout
| Path | Purpose |
|---|---|
| `api/` | Rust (`axum`) API: job queue, SQLite (`0001`–`0003` migrations incl. live source graph), SSE progress & replay, contract patch validation, cache, re-runs |
| `contracts/` | Rust contract types (source of truth), generated `openapi.json` and TypeScript `ts/api.d.ts`, and `fixtures/analysis.json` |
| `worker/` | Python FastAPI stage worker (`POST /stages/{name}` dispatches to `pipeline.<stage>.run`) |
| `pipeline/` | Stages (`extract`, `understand`, `retrieve`, `story`, `signals`, `score`, `explain`, `graph`) + shared `common/` helpers |
| `web/` | React + TypeScript + Vite UI: live SSE stream, noisy-OR combined hero, code-point span reader, coverage & waterfall views, `/metrics`, zoomable `/sources` map |
| `extension/` | Manifest V3 browser extension & bookmarklet for 1-click page, selection, and meme/image checks |
| `evals/` | 284-item multilingual benchmark (ClaimReview, EUvsDisinfo, VIGINUM Portal Kombat, 6 hard-negative sets), symmetry check, runner, `metrics.json`, `graph.json` |
| `deploy/` | Multi-stage Dockerfiles (`api`, `worker`, `caddy`), `compose.yaml`, `Caddyfile`, VPS runbook |
| `SPEC.md` / `DECISIONS.md` | Product specification and append-only engineering decision log |
| `docs/` / `plans/` | Challenge research, AI core signal catalogue (`docs/ai-core.md`), source-graph & persuasion analysis plans, pitch & submission materials (`docs/pitch/`) |

## License
MIT, see `LICENSE`.

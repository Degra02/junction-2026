# Decisions

One line per decision, newest last. Agents re-read this at the start of every round.

Format: `- <day HH:MM> — <decision> — <owner>`

- Wed 11.11 — Toolchain pinned in `mise.toml` (node 26, python 3.14, bun 1.4, uv 0.13, gitleaks 8); no local DB containers — team
- Wed 11.11 — All model calls go through one OpenAI-compatible client (`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`) — team
- Fri 20:15 — Main challenge: Hostinger "Decode the Noise"; tech challenges are uncapped — team
- Fri 20:15 — Everything in English: code, comments, hooks, docs, UI, submission — team
- Fri 20:30 — Product: Trust the source + Spot the swarm + Name the technique on web content (URL/text/screenshot); scope and sponsor roles in `SPEC.md` — team
- Fri 20:30 — Tech challenges: tier 1 Nemotron, Context.dev, Oxylabs, Gemma, Verda; tier 2 Modal, Aiven; tier 3 Codex, CRACI; dropped Gemini, Cloudinary, Arduino, Atech — team
- Sat 00:58 — Direction: context-aware propaganda detection pipeline per `docs/plan.md` (decisions D1–D17 in its section 13); supersedes the two Fri 20:30 lines; `SPEC.md` is rewritten from the plan by mosearc — team
- Sat 00:58 — D1 Input order: pasted text (MVP), then article URL, then image (OCR) — team
- Sat 00:58 — D2 Any language, with support tiers "evaluated / supported, not evaluated / unsupported" shown to the user — team
- Sat 00:58 — D3 Both dimensions in the MVP, single-actor and coordinated, scored separately — team
- Sat 00:58 — D4 No "propaganda / not" label (it is not ground truth): a confidence score per dimension plus the evidence list; "Not enough evidence" when abstaining — team
- Sat 00:58 — D5 Pretrained Hugging Face models for the signals; only the logistic-regression combiner is trained — team
- Sat 00:58 — D6 Technique model `Mishtar4/persuasion-detector-xlm-roberta`, after a CPU latency check and a spot check outside its training languages — team
- Sat 00:58 — D7 Free sources first, plus Oxylabs ($500 Flexible plan with `JUNCTION2026`; cancel right after the event); no Context.dev — team
- Sat 00:58 — D8 Fact checks: Google Fact Check Tools API plus site search on checkers missing from it — team
- Sat 00:58 — D9 Our own measurable outlet types; no political-bias ratings — team
- Sat 00:58 — D10 n8n only for scheduled ingestion, phase 2 — team
- Sat 00:58 — D11 SQLite on the VPS — team
- Sat 00:58 — D12 LLM endpoint: Hostinger AI Router via `LLM_BASE_URL` — team
- Sat 00:58 — D13 No GPU, no fine-tuning for now — team
- Sat 00:58 — D14 English UI; content analysis in any language; LLM explanation in the user's language as an option — team
- Sat 00:58 — D15 Tech challenges kept: Oxylabs and Google MLH "Best Use of Gemini API" (Gemini with Google Search grounding as a retrieval adapter, other uses possible); the rest of the Fri 20:30 tier list is dropped — team
- Sat 00:58 — D16 Roles: Integrator Degra02; AI core Lyreplus (understanding, signals, scoring, explanation); Product ck-lithium (extraction, retrieval, story clustering until the Sat 12:00 freeze, then `web/`); Problem mosearc (`evals/`, `SPEC.md`, pitch) — team
- Sat 03:20 — Backend: Rust (axum) API owns jobs, SQLite, SSE progress and contract validation; it calls one Python FastAPI worker per stage (`POST /stages/{name}`). Replaces "API (FastAPI)" in `docs/plan.md` §7; rationale in `plans/backend-approaches.md` — Degra02
- Sat 03:20 — Contract: Rust types in `contracts/` are the source of truth; `mise run contracts` generates `contracts/openapi.json`, `pipeline/common/contracts.py` (pydantic) and `contracts/ts/api.d.ts`; CI fails on drift — Degra02
- Sat 03:20 — Stage interface: `pipeline/<owner pkg>/__init__.py: run(analysis) -> <Stage>Patch` (signals: `run_single` / `run_coordinated`); missing stages are skipped, not faked (`AGENTS.md` "Pipeline stages") — Degra02
- Sat 03:20 — Rust tests run with cargo-nextest; pre-commit runs rustfmt + clippy `-D warnings` when Rust files are staged — Degra02
- Sat 03:20 — Deploy: images built in GitHub Actions, pushed to GHCR, pulled on the VPS over SSH (`deploy/`); Caddy terminates TLS; nothing compiles on the VPS — Degra02
- Sat 03:20 — Ownership: `worker/` and `pipeline/common/` (generated contracts, shared clients) belong to the integrator — Degra02
- Sat 12:20 — Contract: `retrieve` carries everything fetched from the web: `context[].tracking_ids`, `context[].fact_check` (claim, rating, publisher) and `sources[]` (per-domain registration date, first certificate, outlet type, country, known network); signal stages do no network I/O — Degra02
- Sat 12:20 — Contract validation: evidence needs at least one source ref; a breakdown family must belong to its score's dimension; quotations (12+ characters in double quotes or guillemets) in the explanation must be verbatim in the document, the context or an evidence detail — Degra02
- Sat 12:20 — Cache: only analyses without a failed step are reused; `?force=true` runs again; `POST /api/analyses/{id}/rerun?from=<stage>` re-runs from a stage on the stored earlier output; `events?replay=true` plays a finished analysis back — Degra02
- Sat 12:20 — Stage errors: only `StageError` messages reach the public record; other exceptions show their type, details stay in the worker log — Degra02
- Sat 12:20 — Limits: 30 new analyses/min per client (IPv4 address or IPv6 /64) and 600/h in total, cached results free; 4 analyses at once, 1 model stage at a time; 300 s budget per analysis; `STAGES_DISABLED` kill switch — Degra02
- Sat 12:20 — Shared Python helpers in `pipeline/common/`: `llm` (the one client, `openai` SDK), `spans`, `errors`, `progress`, `net`, `fixtures`; torch resolves from the CPU wheel index — Degra02
- Sat 12:20 — Web: `web/` builds with `bun run build` into `web/dist`, served by Caddy at `/`; the UI calls `/api/...` on the same origin — Degra02

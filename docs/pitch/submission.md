# Submission text

Fields of the Junction platform (`docs/junction-2026.md`): name ≤ 100 characters, punchline ≤ 300, description ≤ 3,000. Numbers come from the committed `evals/metrics.json` (284 items, weights fitted on the same set with 5-fold cross-validation, `df75a3a`); recompute them here if the metrics change.

## Name (11 characters)
The4thLover

## Punchline (139 characters)
Paste a link, text, or meme. See how everyone else covered it, what was copied across sites, and how sure we are — with every source shown.

## Track & Challenges to Select on Junction Platform
- **Track**: Agentic AI
- **Main Challenge**: Hostinger — *Decode the Noise*
- **Tech Challenges (3)**:
  1. **Oxylabs** — *Best agentic usecase of Oxylabs Web API* (`POST /search/instant` + `POST /scrape`)
  2. **Google DeepMind** — *Best Use of Gemini API* (`generateContent` vision + multimodal `rhetoric` rater + NLI verifier + structured multilingual `understand`/`explain`)
  3. **OpenAI** — *Best Use of Codex* (48h contract-first multi-agent workflow across 70+ PRs)

## Links
- Demo: <https://the4thlover.tech>
- Source: <https://github.com/Degra02/junction-2026> (MIT)

## Description (2,853 characters)
A reader sees an article, post, or meme and cannot tell whether it is manipulation by its author or one node of a coordinated network. Checking that by hand takes hours of OSINT; asking an LLM about the text alone is language-biased, prompt-injectable, and unverifiable.

The4thLover takes a link, text, or meme in any language (via web or browser extension) and gathers live context: curated RSS feeds, GDELT, Google Fact Check Tools, and the Oxylabs Web API (`POST /search/instant` for exact-phrase copy search across the web and X/Reddit, multilingual news search, and ClaimReview site search; `POST /scrape` to read bot-challenged or JS-gated pages cleanly without Chromium). Per domain it checks RDAP age, Certificate Transparency history, outlet type (wire agency, fact-checker, satire…), and VIGINUM's Portal Kombat list.

From that evidence it scores two calibrated logistic-regression models combined via noisy-OR — content manipulation (persuasion techniques, emotional tone vs story peers, claims contradicted by coverage or fact-checks) and coordinated amplification (5-gram text reuse across sites or social accounts, 6h timing bursts, shared GA/GTM/AdSense IDs, listed networks) — shown with its log-odds breakdown and source links, never a binary "propaganda" verdict. When coverage is too thin for a percentage, it abstains rather than guessing and surfaces detected persuasion techniques directly. Every analysis also grows a live SQLite source graph (`/sources`) tying outlets by shared tracker IDs, copied text, and translations — uncovering RT mirror domains via shared analytics tags with zero strong false ties on hard negatives.

Google's Gemini API powers four bounded stages where every quote is verified verbatim by Rust code-point span checks (so the model never hallucinates citations or sets raw scores): multimodal meme OCR and implied-argument extraction (`generateContent`), a multimodal SemEval-2023 `rhetoric` rater over text and image together, selective cross-lingual NLI contradiction verification, and multilingual claim extraction and summaries (`gemini-3.1-flash-lite` / `gemini-4-hydrogen`).

Evaluated on 284 third-party-labelled items in 12 languages plus adversarial hard negatives (fact-checks quoting hoaxes, wire copy, press releases, satire, op-eds, emotional reporting): single-actor precision 0.98, FPR 0.03 (CV AUC 0.98; 0.84 without fact-checks; 43% scored, 56% abstained); coordinated CV AUC 1.00 (0.38 without VIGINUM; 0 hard-negative FPs), published at `/metrics`.

Live on one Hostinger KVM 2 VPS (2 vCPU, 8 GB, no GPU; Caddy, Rust/axum API, SQLite, Python CPU worker, Hostinger AI Router). Built in 48h across 70+ PRs using OpenAI Codex in a contract-first multi-agent workflow (`contracts/` Rust types generating OpenAPI, Pydantic, and TypeScript schemas, gated by 55 Rust and 524 Python tests).

## Challenges & Partner Integrations (Technical Breakdown)

| Challenge | How it is used in The4thLover |
|---|---|
| **Hostinger — Decode the Noise** *(Agentic AI Track)* | Deployed live on a single **Hostinger KVM 2 VPS** (2 vCPU, 8 GB RAM, no GPU) behind Caddy TLS (`deploy/`): Rust (`axum`) API + SQLite, Python FastAPI worker running CPU models, and LLM calls routed via **Hostinger AI Router** (`https://router.hostinger.com/v1`). Tackles *Name the technique*, *Trust the source*, and *Spot the swarm*, backed by adversarial hard-negative benchmarks (`/metrics`). |
| **Oxylabs — Best agentic usecase of Oxylabs Web API** | Runtime web verification (`OXYLABS_TOKEN` via `https://api-aistudio.oxylabs.io`):<br>• **`POST /search/instant`** (`pipeline/retrieve/oxylabs.py`, `pipeline/retrieve/social.py`): exact-phrase search to uncover copied passages across websites and X/Reddit accounts, multilingual news coverage beyond RSS feeds, and site-scoped ClaimReview fact-check search.<br>• **`POST /scrape`** (`pipeline/extract/scraper.py`): clean Markdown/text extraction on bot-challenged or JS-gated pages (e.g. France24, TASS) with zero headless browser overhead.<br>Every claim, copy, and reason links directly to its retrieved source URL. |
| **Google DeepMind — Best Use of Gemini API** | Four bounded stages where Gemini never sets raw scores and every quotation is verified verbatim by Rust code-point span checks (`contracts/src/apply.rs`, `pipeline/common/spans.py`):<br>• **Multimodal meme/screenshot vision** (`pipeline/extract/vision.py`, `generateContent`): OCR, neutral `[Visual context]`, satire-meme guard, and implied visual argument extraction.<br>• **Multimodal `rhetoric` rater** (`pipeline/signals/rhetoric.py`): inspects text + image together for SemEval-2023 persuasion categories, dropping quoted-speech hits and non-verbatim spans.<br>• **Selective NLI cascade** (`pipeline/signals/judge.py`) + **structured multilingual `understand` & `explain`** (`gemini-3.1-flash-lite` / `gemini-4-hydrogen`). |
| **OpenAI — Best Use of Codex** | Engineered for 4-person parallel agent development in 48 hours (`AGENTS.md`, `DECISIONS.md`, `docs/next-steps.md`): Rust types in `contracts/` serve as single source of truth (`mise run contracts` generates `openapi.json`, Pydantic `contracts.py`, and TypeScript `api.d.ts`), each stage tests in isolation against `contracts/fixtures/analysis.json`, and CI enforces `mise run check` (Rust `nextest` and Python `pytest` suites, `clippy -D warnings`, `ruff`, contract-drift checks, and `gitleaks`). |

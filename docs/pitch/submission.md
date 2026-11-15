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

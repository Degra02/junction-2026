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

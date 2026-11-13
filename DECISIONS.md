# Decisions

One line per decision, newest last. Agents re-read this at the start of every round.

Format: `- <day HH:MM> — <decision> — <owner>`

- Wed 11.11 — Toolchain pinned in `mise.toml` (node 26, python 3.14, bun 1.4, uv 0.13, gitleaks 8); no local DB containers — team
- Wed 11.11 — All model calls go through one OpenAI-compatible client (`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`) — team
- Fri 20:15 — Main challenge: Hostinger "Decode the Noise"; tech challenges are uncapped — team
- Fri 20:15 — Everything in English: code, comments, hooks, docs, UI, submission — team
- Fri 20:30 — Product: Trust the source + Spot the swarm + Name the technique on web content (URL/text/screenshot); scope and sponsor roles in `SPEC.md` — team
- Fri 20:30 — Tech challenges: tier 1 Nemotron, Context.dev, Oxylabs, Gemma, Verda; tier 2 Modal, Aiven; tier 3 Codex, CRACI; dropped Gemini, Cloudinary, Arduino, Atech — team

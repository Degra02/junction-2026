# Decisions

One line per decision, newest last. Agents re-read this at the start of every round.

Format: `- <day HH:MM> — <decision> — <owner>`

- Wed 11.11 — Toolchain pinned in `mise.toml` (node 26, python 3.14, bun 1.4, uv 0.13, gitleaks 8); no local DB containers — team
- Wed 11.11 — All model calls go through one OpenAI-compatible client (`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`) — team
- Fri 13.11 19:00 — Partner challenge: Hostinger — team
- Fri 13.11 19:00 — Direction "Clean the traffic" (web-log bot detection); revisit only if the Hostinger booth says otherwise — degra
- Fri 13.11 19:00 — LLM explains verdicts, never sets them; default endpoint Hostinger AI Router — degra

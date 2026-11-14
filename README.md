# Junction 2026

Team workspace for Junction 2026 (Espoo, 13–15 Nov 2026), Hostinger challenge "Decode the Noise". A pipeline that takes one piece of online content and shows how strongly it carries signs of propaganda by its author and of coordinated propaganda: a confidence score per dimension, built from evidence gathered live about the same event, with every source shown. Plan: `docs/plan.md`.

## Quickstart
```sh
mise trust && mise run setup   # pinned node/python/bun/uv/rust/nextest/gitleaks, git hooks, uv sync
cp .env.example .env           # fill from the team password manager
mise run check                 # what CI runs
mise run dev                   # worker :8001 + API :8080, docs at http://127.0.0.1:8080/api/docs
```

## Layout
| Path | Purpose |
|---|---|
| `api/` | Rust (axum) API: jobs, queue, SQLite, SSE progress, patch validation, cache, re-runs, replays, usage stats; drives the worker |
| `contracts/` | Rust contract types (source of truth), the generated `openapi.json` and TS types, and `fixtures/analysis.json` (the example record stages are tested against) |
| `worker/` | Python FastAPI stage worker: `POST /stages/{name}` calls `pipeline.<stage>.run` |
| `pipeline/` | Pipeline stages, one package per owner. `pipeline/common/`: generated `contracts.py`, the LLM client (`llm`), span locator (`spans`), `StageError`, progress notes, URL guard (`net`), fixture loader |
| `deploy/` | Dockerfiles, Compose, Caddyfile, VPS runbook |
| `plans/` | Integrator stack, backend comparison, implementation practices |
| `SPEC.md` | Problem, demo moment, scope (being rewritten from `docs/plan.md`) |
| `DECISIONS.md` | Append-only decision log |
| `AGENTS.md` / `CLAUDE.md` | Rules for coding agents |
| `docs/junction-2026.md` | Event schedule, judging, sponsors, challenges |
| `docs/hostinger-challenge.md` | Hostinger challenge research: datasets, methods, risks, booth questions |
| `docs/plan.md` | Project description, pipeline, scoring, evaluation, hosting, roles, timeline, decisions for review |
| `docs/directions.md` | Earlier direction comparison, judges' feedback (background) |
| `docs/playbook.md` | Roles, 48h timeline, agent workflow, submission checklist |
| `docs/setup.md` | Machine setup, sandboxed agents, accounts to create |
| `evals/` | Eval harness, dataset download, hard-negative sets — see `evals/README.md` |
| `docs/pitch/` | Pitch deck, demo script, submission text |
| `mise.toml` | Pinned toolchain, env loading, tasks |
| `.devcontainer/` | Dev container: mise + pinned toolchain, runs setup on create |
| `.githooks/` | Pre-commit: block commits to `main`, scan for secrets, rustfmt + clippy on Rust changes |
| `.github/workflows/` | `ci.yml`: `mise run check`; `deploy.yml`: images to GHCR, SSH deploy from `main` |

## License
MIT, see `LICENSE` (Junction submissions are open-sourced under MIT). The copyright line lists GitHub handles; replace them with full names before submitting if the team prefers.

# Junction 2026

Team workspace for Junction 2026 (Espoo, 13–15 Nov 2026). Project to be defined at the event — see `SPEC.md`.

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
| `api/` | Rust (axum) API: jobs, SQLite, SSE progress, patch validation; drives the worker |
| `contracts/` | Rust contract types (source of truth) and the generated `openapi.json` and TS types |
| `worker/` | Python FastAPI stage worker: `POST /stages/{name}` calls `pipeline.<stage>.run` |
| `pipeline/` | Pipeline stages, one package per owner; `pipeline/common/contracts.py` is generated |
| `deploy/` | Dockerfiles, Compose, Caddyfile, VPS runbook |
| `plans/` | Integrator stack, backend comparison, implementation practices |
| `SPEC.md` | Problem, demo moment, scope — filled Friday evening |
| `DECISIONS.md` | Append-only decision log |
| `AGENTS.md` / `CLAUDE.md` | Rules for coding agents |
| `docs/junction-2026.md` | Event schedule, judging, sponsors, challenges |
| `docs/hostinger-challenge.md` | Hostinger challenge research: datasets, methods, risks, booth questions |
| `docs/plan.md` | Project description, pipeline, scoring, evaluation, hosting, roles, timeline, decisions for review |
| `docs/directions.md` | Earlier direction comparison, judges' feedback (background) |
| `docs/playbook.md` | Roles, 48h timeline, agent workflow, submission checklist |
| `docs/setup.md` | Machine setup, sandboxed agents, accounts to create |
| `mise.toml` | Pinned toolchain, env loading, tasks |
| `.devcontainer/` | Dev container: mise + pinned toolchain, runs setup on create |
| `.githooks/` | Pre-commit: block commits to `main`, scan for secrets, rustfmt + clippy on Rust changes |
| `.github/workflows/` | `ci.yml`: `mise run check`; `deploy.yml`: images to GHCR, SSH deploy from `main` |

## License
Junction submissions are open-sourced under MIT; add a `LICENSE` with the team names before submitting.

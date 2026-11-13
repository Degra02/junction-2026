# Junction 2026

Team workspace for Junction 2026 (Espoo, 13–15 Nov 2026). Project to be defined at the event — see `SPEC.md`.

## Quickstart
```sh
mise trust && mise run setup   # pinned node/python/bun/uv/gitleaks + git hooks
cp .env.example .env           # fill from the team password manager
mise run check                 # what CI runs
```

## Layout
| Path | Purpose |
|---|---|
| `SPEC.md` | Problem, demo moment, scope — filled Friday evening |
| `DECISIONS.md` | Append-only decision log |
| `AGENTS.md` / `CLAUDE.md` | Rules for coding agents |
| `docs/junction-2026.md` | Event schedule, judging, sponsors, challenges |
| `docs/hostinger-challenge.md` | Hostinger challenge research: datasets, methods, risks, booth questions |
| `docs/playbook.md` | Roles, 48h timeline, agent workflow, submission checklist |
| `docs/setup.md` | Machine setup, sandboxed agents, accounts to create |
| `mise.toml` | Pinned toolchain, env loading, tasks |
| `.devcontainer/` | Dev container: mise + pinned toolchain, runs setup on create |
| `.githooks/` | Pre-commit: block commits to `main`, scan for secrets |
| `.github/workflows/ci.yml` | `mise run check` on PRs and `main` |

## License
Junction submissions are open-sourced under MIT; add a `LICENSE` with the team names before submitting.

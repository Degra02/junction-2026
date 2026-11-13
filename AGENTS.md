# Junction 2026 — agent instructions

48h hackathon, team of 4, every person drives coding agents. Speed matters, but `main` must always demo.

## Read first
- `SPEC.md` — the problem, the demo moment, what is out of scope. Do not build beyond it.
- `DECISIONS.md` — decisions already made. Do not relitigate them; ask the integrator.
- `docs/` — event facts, sponsors, playbook, setup.

## Commands
- `mise run setup` — install pinned tools (node, python, bun, uv, gitleaks) and enable git hooks.
- `mise run check` — what CI runs. Must pass before asking for a merge.
- `mise tasks` — list everything else. Add new commands as mise tasks, not ad-hoc scripts.
- Python deps: `uv add <pkg>`; JS deps: `bun add <pkg>` (or the package manager recorded in `DECISIONS.md`).

## Git
- Work on your own branch (`<person>/<topic>`); never commit or push to `main` (the pre-commit hook blocks it).
- Small commits; merge to `main` via PR every ~2h round. Rebase on `main` before opening the PR.
- Never `push --force`, `reset --hard`, or delete branches you did not create.

## Ownership
Edit only the folders your owner is responsible for. Shared files need the integrator: API contracts, dependency manifests, `mise.toml`, CI, `AGENTS.md`, `SPEC.md`.

| Role | Person | Owns |
|---|---|---|
| Integrator | Degra02 | `main`, `contracts/`, `api/`, `deploy/`, `mise.toml`, CI, `AGENTS.md`, `DECISIONS.md` |
| AI core | Lyreplus | prompts, `pipeline/understand/`, `pipeline/signals/`, `pipeline/score/`, `pipeline/explain/` |
| Product | ck-lithium | `pipeline/extract/`, `pipeline/retrieve/`, `pipeline/story/`; `web/` and the demo path after the Sat 12:00 spec freeze |
| Problem / pitch | mosearc | `SPEC.md`, `evals/` (labelled sets, fixtures, eval harness), demo data, end-to-end tests, `docs/pitch/` |

Full split and timeline: `docs/plan.md` sections 10–11.

## Secrets
- Read keys from the environment (`.env`, loaded by mise). Never print, log, hard-code, or commit them.
- The repo is published under MIT at submission. Anything committed is public.

## Model calls
- One OpenAI-compatible client configured by `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`; switching provider is a config change, not a code change.

## Definition of done
- You ran it: the command, test, or demo path that exercises the change, with output.
- `mise run check` passes.
- No placeholder code, fake success paths, or mocks left on the demo path unless `SPEC.md` says so.

# Junction 2026 — agent instructions

48h hackathon, team of 4, every person drives coding agents. Speed matters, but `main` must always demo.

## Read first
- `SPEC.md` — the problem, the demo moment, what is out of scope. Do not build beyond it.
- `DECISIONS.md` — decisions already made. Do not relitigate them; ask the integrator.
- `docs/` — event facts, sponsors, playbook, setup.

## Commands
- `mise run setup`: install pinned tools (node, python, bun, uv, rust, cargo-nextest, gitleaks), enable git hooks, `uv sync`.
- `mise run check`: what CI runs (gitleaks, rustfmt, clippy, nextest, ruff, pytest, contract drift). Must pass before asking for a merge.
- `mise run dev`: worker (:8001) and API (:8080) locally; API docs at <http://127.0.0.1:8080/api/docs>.
- `mise run contracts`: regenerate `contracts/openapi.json`, `pipeline/common/contracts.py`, `contracts/ts/api.d.ts` from the Rust types. Never edit those files by hand.
- `mise tasks`: list everything else. Add new commands as mise tasks, not ad-hoc scripts.
- Python deps: `uv add <pkg>`; JS deps: `bun add <pkg>`; Rust deps: `[workspace.dependencies]` in `Cargo.toml` (integrator).
- Rust tests run with `cargo nextest run`, not `cargo test`. The pre-commit hook runs `cargo fmt --check` and clippy (`-D warnings`) when Rust files are staged.

## Git
- Work on your own branch (`<person>/<topic>`); never commit or push to `main` (the pre-commit hook blocks it).
- Small commits; merge to `main` via PR every ~2h round. Rebase on `main` before opening the PR.
- Never `push --force`, `reset --hard`, or delete branches you did not create.

## Ownership
Edit only the folders your owner is responsible for. Shared files need the integrator: API contracts, dependency manifests, `mise.toml`, CI, `AGENTS.md`, `SPEC.md`.

| Role | Person | Owns |
|---|---|---|
| Integrator | Degra02 | `main`, `contracts/`, `api/`, `worker/`, `pipeline/common/`, `deploy/`, `Cargo.toml`, `pyproject.toml`, `mise.toml`, CI, `AGENTS.md`, `DECISIONS.md` |
| AI core | Lyreplus | prompts, `pipeline/understand/`, `pipeline/signals/`, `pipeline/score/`, `pipeline/explain/` |
| Product | ck-lithium | `pipeline/extract/`, `pipeline/retrieve/`, `pipeline/story/`; `web/` and the demo path after the Sat 12:00 spec freeze |
| Problem / pitch | mosearc | `SPEC.md`, `evals/` (labelled sets, fixtures, eval harness), demo data, end-to-end tests, `docs/pitch/` |

Full split and timeline: `docs/plan.md` sections 10–11.

## Pipeline stages
The Rust API (`api/`) runs the stages in order and calls the Python worker (`worker/`) once per stage: `POST /stages/{name}` with the full `Analysis`. A stage is a function in its owner's package:

| Stage | Function | Returns |
|---|---|---|
| extract | `pipeline/extract/__init__.py: run` | `ExtractPatch` |
| understand | `pipeline/understand/__init__.py: run` | `UnderstandPatch` |
| retrieve | `pipeline/retrieve/__init__.py: run` | `RetrievePatch` |
| story | `pipeline/story/__init__.py: run` | `StoryPatch` |
| signals_single / signals_coordinated | `pipeline/signals/__init__.py: run_single` / `run_coordinated` | `SignalsPatch` |
| score | `pipeline/score/__init__.py: run` | `ScorePatch` |
| explain | `pipeline/explain/__init__.py: run` | `ExplainPatch` |

- Signature: `def run(analysis: Analysis) -> XPatch` (or `async def` for I/O-bound work), types from `pipeline.common.contracts`. CPU-bound code must be a plain `def`: the worker runs it in a thread.
- Until the function exists the step shows "not implemented yet" and the rest still runs. Load models at import time; the worker imports every stage at startup.
- The API validates every patch: duplicate IDs, an evidence family outside the stage's dimension or an invalid score fail the step; claims that are not verbatim at their span, evidence citing unknown context or non-verbatim quotes, and reasons without valid evidence IDs are dropped and listed in the step's `detail`.
- Field meanings are documented in `contracts/src/analysis.rs` and in the generated `pipeline/common/contracts.py`. Need a new field? Ask the integrator.

## Secrets
- Read keys from the environment (`.env`, loaded by mise). Never print, log, hard-code, or commit them.
- The repo is published under MIT at submission. Anything committed is public.

## Model calls
- One OpenAI-compatible client configured by `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`; switching provider is a config change, not a code change.

## Definition of done
- You ran it: the command, test, or demo path that exercises the change, with output.
- `mise run check` passes.
- No placeholder code, fake success paths, or mocks left on the demo path unless `SPEC.md` says so.

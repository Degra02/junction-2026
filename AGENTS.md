# Junction 2026 — agent instructions

48h hackathon, team of 4, every person drives coding agents. Speed matters, but `main` must always demo.

## Read first
- `docs/next-steps.md` — **your current tasks**, per person, updated by the integrator every round. Start here.
- `docs/plan.md` — the decided project: pipeline, scoring, scope, roles. Do not build beyond it. `SPEC.md` is the product spec derived from it.
- `DECISIONS.md` — decisions already made. Do not relitigate them; ask the integrator.
- `docs/ai-core.md` — signal catalogue with value scales, scoring formula, models, and what `extract`, `retrieve` and `story` must provide for the signals.
- `plans/source-graph.md` — the source graph (`pipeline/graph/`, `GET /api/graph`): what is built, the model, the phases. Its tasks and rules are in `docs/next-steps.md` → "Source graph".
- `docs/` — event facts, sponsors, setup. `docs/[DEPRECATED]playbook.md` is superseded by this file and `docs/next-steps.md`.

## Commands
- `mise run setup`: install pinned tools (node, python, bun, uv, rust, cargo-nextest, gitleaks), enable git hooks, `uv sync`.
- `mise run check`: what CI runs (gitleaks, rustfmt, clippy, nextest, ruff, pytest, contract drift). Must pass before asking for a merge.
- `mise run dev`: worker (:8001) and API (:8080) locally; API docs at <http://127.0.0.1:8080/api/docs>.
- `mise run web:dev`: the web UI on :5173 with `/api` proxied to the local API; `VITE_API_TARGET=https://the4thlover.tech mise run web:dev` shows live data. `mise run web:build` typechecks against `contracts/ts/api.d.ts` and builds `web/dist` (the caddy image build in CI runs the same).
- `mise run contracts`: regenerate `contracts/openapi.json`, `pipeline/common/contracts.py`, `contracts/ts/api.d.ts` from the Rust types. Never edit those files by hand.
- `mise run graph:build -- evals/results/fit.jsonl --labelled evals/labelled.jsonl`: rebuild `evals/graph.json` (served at `/api/graph`) from stored analyses. Never edit that file by hand.
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
| AI core | Lyreplus | prompts, `pipeline/understand/`, `pipeline/signals/`, `pipeline/score/`, `pipeline/explain/`, `pipeline/graph/` |
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
- The API validates every patch. These fail the step: duplicate IDs (claims, context, evidence, `sources[].domain`), an evidence family or a score breakdown family outside the stage's dimension, an invalid score. These are dropped and listed in the step's `detail`: claims that are not verbatim at their span; evidence with no source ref, an unknown context ID or a non-verbatim quote; reasons without valid evidence IDs; reasons (and the summary, which is blanked) containing a quotation that is not verbatim in the document, the context or an evidence detail. A quotation is 12 or more characters inside double quotes or guillemets.
- Everything fetched from the web comes from `retrieve`: `context[]` (each item with its `tracking_ids`, and `fact_check` when it is a fact-check) and `sources[]` (one profile per outlet domain: registration date, first certificate, outlet type, country, known network). Signal stages compute from the record only and do no network I/O.
- Field meanings are documented in `contracts/src/analysis.rs` and in the generated `pipeline/common/contracts.py`. Need a new field? Ask the integrator.

### Shared helpers (`pipeline/common/`, integrator-owned)
- `llm`: `ask_json(Schema, system=..., user=...)`, `ask_text(...)` and their `_async` variants. The only LLM client; analysed content goes in `user`, never in `system`.
- `spans`: `claim(document, "cl1", passage)` and `locate(document, passage)` return the exact code-point span of a passage. Never ask a model for offsets.
- `errors.StageError("plain message")`: the only exception text users see. Any other exception is public as its type only ("the stage failed (TimeoutError)"), with the details in the worker log. Never put keys or request URLs in a `StageError`.
- `progress.report("9 sources so far")`: a live note under the running step in the UI.
- `net.assert_public_url(url)`: call before fetching the analysed URL and on every redirect hop.
- `fixtures.example_analysis()`: a finished example `Analysis` (`contracts/fixtures/analysis.json`) to test a stage without the others.

### Iterating on a stage
- `POST /api/analyses/{id}/rerun?from=<stage>` runs a finished analysis again from that stage on the stored output of the earlier ones (new ID): change a signal, the combiner or the explanation and compare on the same retrieved context.
- `POST /api/analyses?force=true` ignores the result cache. A result with a failed step is never reused.
- Eval runs go against a local API with the limits off: see "Local" in `deploy/README.md`.

## Secrets
- Read keys from the environment (`.env`, loaded by mise). Never print, log, hard-code, or commit them.
- The repo is published under MIT at submission. Anything committed is public.

## Model calls
- One OpenAI-compatible client, `pipeline/common/llm.py`, configured by `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`; switching provider is a config change, not a code change.

## Web UI (`web/`)
- `bun run build` must write the static site to `web/dist`; the deploy builds it into the Caddy image (`deploy/caddy.Dockerfile`), which serves it at `/` with `index.html` as the fallback.
- Call the API with relative URLs (`/api/...`); in development proxy `/api` to `http://127.0.0.1:8080` (there is no CORS). Types: `contracts/ts/api.d.ts`.
- Progress: `new EventSource("/api/analyses/{id}/events")` sends `snapshot`, `queue`, `step` and `done`; add `?replay=true` to play a finished analysis back for the demo.
- Span offsets count code points: highlight with `Array.from(paragraph).slice(start, end)`, not `paragraph.slice`.

## Definition of done
- You ran it: the command, test, or demo path that exercises the change, with output.
- `mise run check` passes.
- No placeholder code, fake success paths, or mocks left on the demo path unless `SPEC.md` says so.

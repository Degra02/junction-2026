# Backend approaches — comparison

Owner: Degra02. Sat 14.11. Compares the proposed stack (`plans/integrator-stack.md`) with the alternatives on performance, correctness, and how reliably a coding agent can implement it in this repo. Measurements are from throwaway prototypes on a 16-core dev machine; anything not measured is marked [estimate].

## Approaches
| ID | Shape |
|---|---|
| **A** (proposed) | Rust axum orchestrator + one Python FastAPI worker exposing `/stages/*` |
| B | Python monolith: FastAPI API with the stages and models in the same process (`docs/plan.md` §7 as written) |
| C | Same shape as A, orchestrator in Python (FastAPI) instead of Rust |
| D | Same shape as A, orchestrator in TypeScript (Bun + Hono) |
| E | Same shape as A, orchestrator in Go |
| F | Rust all-in: models via `candle` / `ort`, retrieval in Rust |
| G | Rust API embedding the Python pipeline through PyO3 |

## What was measured
| Measurement | Result |
|---|---|
| Rust skeleton (axum 0.8.9, utoipa 6 + utoipa-axum 0.3 + Scalar, sqlx 0.9 SQLite WAL, reqwest 0.13, tower-http 0.7, SSE, semaphore, per-stage worker calls, ~190 lines) | **Compiled on the first attempt, 0 clippy warnings**; OpenAPI 3.1 dump with 3 paths and 5 schemas; smoke run: `POST /api/analyses` → 202, job ran both stages, worker absent → steps `failed`, record `done`, `/api/docs` 200 |
| Rust cold debug build, 16 cores | 52.5 s, peak 573 MB RAM |
| Rust incremental rebuild after touching `main.rs` | 3.4 s |
| Rust cold release build, `-j 4` (GitHub public-repo runner size) | 2 min 21 s, peak 447 MB RAM; stripped binary 10.0 MiB |
| Rust idle RSS (debug build) | 21 MB |
| FastAPI 0.162 + uvicorn idle RSS (Python 3.14.10) | 73 MB |
| Python deps install (`uv`, cold cache) | 2.0 s |
| FastAPI `/health` at idle | p50 1.2 ms, max 6.2 ms |
| FastAPI `/health` while a 2.9 s pure-Python CPU task runs **inside `async def`** | 1 probe completed, **2,893 ms** (event loop frozen for the whole task) |
| Same task offloaded with `asyncio.to_thread` | p50 12.2 ms, max 17.6 ms (GIL contention, loop alive) |
| Per-stage hop cost: pydantic parse + dump + parse of a 206 KiB `Analysis` (20 paragraphs, 30 context articles × 6 KB, 40 evidence items) | 1.55 ms |

## Performance
- **The orchestrator language does not move end-to-end latency.** The budget (≤ 60 s) is spent in CPU inference (XLM-R large over ~20 paragraphs: tens of seconds on 2 vCPU [estimate, `docs/plan.md` §6]) and external APIs (GDELT alone is 1 request / 5 s). API overhead is ~1 ms in every option; the A/C/D/E per-stage hop is ~1.5 ms × 8 stages ≈ 12 ms on the Python side plus localhost HTTP.
- **Memory does not decide it either.** Models are ~6 GB fp32 [estimate] in every option except F. The orchestrator adds 21 MB (Rust), 73 MB (Python), ~30–50 MB (Bun, Go) [estimate].
- **Where performance does differ: event-loop safety.** In B the stages share the API's event loop. One CPU-bound call in `async def` (an easy agent mistake) freezes every request, including the SSE progress stream: measured 2.9 s stall for a 2.9 s task. A, C, D, E keep the API in a separate process, so SSE and `/health` stay responsive whatever the worker does. Torch and tokenizers release the GIL during inference, but Python-side preprocessing (MinHash, scoring, JSON) does not.
- **Build cost is Rust's real performance price.** A cold release build took 2 min 21 s on 4 cores. The repo is private now, and GitHub's private-repo `ubuntu-latest` runner has 2 vCPU (public: 4), so expect roughly double [estimate] until submission makes it public. Mitigation: `Swatinem/rust-cache`, `cargo-chef` layer caching, build images in CI only (never on the 2 vCPU VPS). Python and Go have no comparable cost.
- **F (Rust inference) gains nothing.** `ort` wraps the same ONNX Runtime that Python's `onnxruntime` uses, and HF `tokenizers` is already Rust under Python. `candle` has `xlm_roberta` and `debertav2` implementations, but the custom classifier heads, pooling and thresholds would have to be re-implemented and re-validated against the Python reference. `ort` 2.0 is still a release candidate (rc.15, 19.10.2026).

## Correctness
| Concern | A Rust + worker | B Python monolith | C Python + worker | D Bun + worker | E Go + worker |
|---|---|---|---|---|---|
| Contract source of truth | Rust types → OpenAPI → pydantic + TS (2 codegen hops) | pydantic → OpenAPI → TS (1 hop) | pydantic (1 hop) | zod → OpenAPI → pydantic + TS | Go structs or `oapi-codegen` (2 hops) |
| Type errors caught | At compile time in the orchestrator; pydantic at the worker boundary | Runtime; pyright helps if enforced | Runtime + pyright | Compile time (TS), runtime validation via zod | Compile time |
| Async correctness | `Send`/lifetime bounds reject unsound shared state; CPU work cannot block the API (other process) | Event-loop blocking (measured above); needs discipline | API safe; worker still needs discipline | API safe | API safe |
| Worker OOM / crash | API, DB and SSE survive; step marked `failed`; Docker restarts worker | **Everything dies**: in-flight jobs, SSE, API | Survives | Survives | Survives |
| Partial failure → abstain | Explicit per-stage `Result`, exhaustive `match` | Exceptions; easy to swallow | Exceptions | Exceptions / Result libs | Explicit `err` checks |
| Contract drift between teammates | CI regenerates and diffs | Same | Same | Same | Same |

What the type system does **not** fix in any option: the scoring logic, the verbatim-quote check, wire-copy handling and the eval set live in Python and are tested there. Rust's correctness gain is confined to orchestration, persistence and the public API: the part that must not fall over during the demo.

## Implementation by a coding agent (my capabilities)
- **Rust, these exact versions:** utoipa 6, utoipa-axum 0.3, utoipa-scalar 0.4, sqlx 0.9, reqwest 0.13 and tower-http 0.7 were released in 2026, later than most material I learned from. The prototype exercised all of them and compiled on the first attempt with no clippy warnings, so API drift is low for the surface we need. Remaining risk areas, from experience: utoipa schemas for serde-tagged enums and generics, `tower_governor` key extractors behind Caddy (needs the forwarded-IP extractor), sqlx migrations in Docker. I resolve these by reading docs.rs and iterating against the compiler; the 3.4 s incremental rebuild keeps that loop short.
- **Rust is a good fit for agent work in one specific way:** the compiler rejects whole classes of mistakes (missing match arms, `Send` violations, wrong JSON shapes) before anything runs, which is exactly the "agent claims done without running it" failure in `docs/playbook.md`.
- **Python/FastAPI:** equally fluent, and the worker is Python in every option anyway. Mistakes surface at runtime, so tests carry more weight.
- **TypeScript/Bun, Go:** fluent in both. Neither offers anything A or C lacks here, and Go is not in the pinned toolchain.
- **F and G:** feasible for me, but each is hours of work that does not show up in the demo or the judging criteria.

## Team and schedule
- **Bus factor during sleep shifts** (`docs/playbook.md`: two people sleep 01–06, two 04–09). In A, a broken `api/` at 05:00 must be fixed by someone else's agent in Rust. Their agents can do it; reviewing it is harder for humans who don't read Rust. B and C keep everything in one language. Mitigation for A: keep `api/` small (<1k lines), integration tests runnable with `mise run api:test`, and a short `api/README.md`.
- **Time to a live skeleton:** B is fastest to first deploy (one process, one image). A, C, D and E each add a worker image and a stage API. The prototype shows the Rust part itself takes well under an hour; most of the extra time is the second image and compose wiring, which C pays too.
- **Ownership:** A matches `AGENTS.md` cleanly (only the integrator edits `contracts/` and `api/`). B mixes integrator code and pipeline code in one process, so the boundary becomes import paths rather than an HTTP contract.

## Verdict
| Option | Verdict |
|---|---|
| **A Rust + Python worker** | **Keep.** Same latency as everything else; best orchestration correctness; process isolation for the demo; measured to be implementable quickly at these crate versions. Costs: CI build time and the sleep-shift bus factor. |
| C Python + Python worker | **Fallback.** Same architecture and isolation, one language, one fewer codegen hop. Switch here only if Rust CI time or the bus factor bites; the worker and stage API carry over unchanged. |
| B Python monolith | Reject. Fastest to first deploy, but one blocking call or OOM takes the demo down, and the pipeline/API boundary blurs. |
| D Bun, E Go | Reject. No advantage over A or C for this project; adds a language without your preference behind it. |
| F Rust all-in | Reject. Same inference engine, re-validation work, ownership conflict with AI core. |
| G PyO3 | Reject. Packaging Python + torch inside the Rust image, GIL inside the API process: combines B's failure modes with A's build cost. |

Conditions for A: Rust stays thin (no business logic); the worker is one process; stages are pure `Analysis → StagePatch`; CI uses rust-cache and builds images only in Actions.

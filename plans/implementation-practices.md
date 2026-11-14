# Implementation practices — Rust API + Python worker

Owner: Degra02 (integrator). Sat 14.11. Companion to `plans/integrator-stack.md`. Every claim below was checked against the linked primary source on 14.11 (crate sources unpacked from crates.io where docs were thin); anything not checked is marked [unverified]. Versions are the latest stable on that date.

Version check (crates.io / PyPI / GitHub releases, 14.11): axum 0.8.9, tower-http 0.7.1, tower 0.5.3, tokio 1.54.1, tokio-util 0.7.20, sqlx 0.9.0, utoipa 6.0.0 / utoipa-axum 0.3.0 / utoipa-scalar 0.4.0, reqwest 0.13.5, tower_governor 0.8.0 (axum ^0.8, governor ^0.10), governor 0.10.4, wiremock 0.6.5, axum-test 21.1.0, insta 1.49.0, cargo-nextest 0.9.152, cargo-chef 0.1.78, apalis 1.1.1; fastapi 0.162.7, uvicorn 0.54.0, pydantic 2.14.3, datamodel-code-generator 0.96.0, torch 2.15.0, onnxruntime 1.32.0, uv 0.13.8; openapi-typescript 7.13.0; Caddy 2.11.9; lefthook 2.2.2; docker/build-push-action v7.4.0, setup-buildx-action v4.4.1, login-action v4.8.0, metadata-action v6.2.0, Swatinem/rust-cache v2.9.3.

## Corrections to the current plan
- **Worker base image**: the uv Docker guide now lists only `trixie` variants (`ghcr.io/astral-sh/uv:python3.14-trixie-slim`). `python3.14-bookworm-slim` still resolves on GHCR (HTTP 200), but use trixie to match the documented set and Debian 13 everywhere. <https://docs.astral.sh/uv/guides/integration/docker/>
- **Rust runtime image**: use `gcr.io/distroless/cc-debian13` so its glibc matches the `rust:1` / `lukemathwalker/cargo-chef:latest-rust-1` builder, which the cargo-chef README pairs with a `debian:trixie-slim` runtime. <https://github.com/LukeMathWalker/cargo-chef>
- **Rate limiting**: the workspace pins `governor`, the plan names `tower_governor 0.8`. `tower_governor` defaults pull in `tonic`, so add it as `tower_governor = { version = "0.8", default-features = false, features = ["axum"] }`. See §7.
- **utoipa 6 can emit OpenAPI 3.2** (`OpenApiVersion::Version32`, opt-in). Keep the default 3.1.0: the two codegens are 3.1-oriented. <https://github.com/juhaku/utoipa/blob/master/utoipa/CHANGELOG.md>

## 1. axum 0.8 service structure
- `api/src/lib.rs` exposes `pub fn app(state: AppState) -> Router` and `pub async fn serve(listener, state, shutdown)`. `main.rs` only reads config, initialises tracing, binds and calls `serve`. Tests call the same `app()`/`serve()`, so the middleware stack under test is the production stack. Pattern: axum `examples/testing`. <https://github.com/tokio-rs/axum/blob/main/examples/testing/src/main.rs>
- `AppState { db: SqlitePool, worker: WorkerClient, hub: Arc<ProgressHub>, jobs: Jobs, cfg: Arc<Config> }`, `#[derive(Clone)]`, every field cheap to clone (`Arc` or pool handles). Pass it with `Router::with_state`.
- One `ApiError` enum (`thiserror`) with `impl IntoResponse` returning `(StatusCode, Json<ErrorBody { code, message, request_id }>)`. Register `ErrorBody` as a utoipa schema so the TS client types errors too. Map `sqlx::Error::RowNotFound` → 404 and worker errors → 502; log the source error, never expose it in the body.
- Layer order (outermost first): `SetRequestIdLayer` (`MakeRequestUuid`) → `TraceLayer` (span records `x-request-id`) → `PropagateRequestIdLayer` → `TimeoutLayer::with_status_code(StatusCode::REQUEST_TIMEOUT, 10s)` → `DefaultBodyLimit`/`RequestBodyLimitLayer`. The tower-http docs require request-id before `TraceLayer` for ids to appear in logs. <https://docs.rs/tower-http/0.7.1/tower_http/request_id/index.html>
- Forward the request id to the worker as `x-request-id` and log it in Python: one grep finds both sides of a failing analysis.
- Graceful shutdown: `axum::serve(listener, app).with_graceful_shutdown(signal)` with SIGTERM + Ctrl-C, exactly as the official example. <https://github.com/tokio-rs/axum/blob/main/examples/graceful-shutdown/src/main.rs>
- Pitfalls: `TimeoutLayer::new` is **deprecated since tower-http 0.6.7** (use `with_status_code`). The timeout covers only the time to response headers, so it does not cut SSE bodies; tower-http 0.7 has `ResponseBodyTimeoutLayer`/`ResponseBodyDeadlineLayer` for idle/total body caps. `DefaultBodyLimit` is 2 MB by default (axum tests); set it explicitly to the input cap. <https://docs.rs/tower-http/0.7.1/tower_http/timeout/struct.TimeoutLayer.html> <https://docs.rs/axum/0.8.9/axum/extract/struct.DefaultBodyLimit.html>

## 2. Testing the API
- **Default: real server on `127.0.0.1:0`** (`TcpListener::bind`, read `local_addr()`, `tokio::spawn(serve(..))`, hit it with `reqwest`). It is the only option that exercises hyper framing, SSE chunking, `ConnectInfo` (rate limiter) and graceful shutdown. axum's own testing example does this alongside `oneshot`. <https://github.com/tokio-rs/axum/blob/main/examples/testing/src/main.rs>
- `tower::ServiceExt::oneshot` for fast handler/validation tests (no socket). Do not use it for SSE or rate-limit tests: there is no peer address unless you insert `ConnectInfo` by hand.
- `axum-test 21.1` (axum ^0.8.9) adds a fluent API and a real-HTTP transport mode; nice, but it is another API for teammates' agents to learn. Skip unless tests get repetitive. <https://docs.rs/axum-test/21.1.0/axum_test/>
- **SSE test**: `reqwest` `.bytes_stream()`, split on `\n\n`, parse `event:`/`data:`/`id:`; wrap every read in `tokio::time::timeout(5s, ..)` so a missing event fails instead of hanging. Assert the order snapshot → step events → terminal event, and that a reconnect with `Last-Event-ID` gets no duplicates.
- **wiremock 0.6.5** as the worker: one `MockServer::start().await` per test (each gets its own port, so tests run in parallel); `Mock::given(method("POST")).and(path("/stages/extract")).respond_with(ResponseTemplate::new(200).set_body_json(..)).expect(1)`; `expect` is verified on drop. `set_delay(..)` tests per-stage timeouts; a 500 or malformed body tests "step failed → score abstains". <https://docs.rs/wiremock/0.6.5/wiremock/>
- **SQLite per test**: `tempfile::TempDir` + file DB with the production `SqliteConnectOptions` (WAL included). Keep the `TempDir` alive for the whole test. `#[sqlx::test]` also works for SQLite (it creates `target/sqlx/test-dbs/<test path>.db`, no `DATABASE_URL` needed per the sqlx-sqlite source) but bypasses your pool config. <https://docs.rs/sqlx/0.9.0/sqlx/attr.test.html>
- Pitfall (in-memory): `sqlite::memory:` in sqlx is a named shared-cache DB (`file:sqlx-in-memory-N`, from `sqlx-sqlite/src/options/parse.rs`) that disappears when the **last** pool connection closes. Pool defaults are `min_connections 0`, `idle_timeout 10 min`, so an idle pool silently loses the DB. It also never runs in WAL mode, so it hides the locking behaviour you ship.
- **nextest** `.config/nextest.toml`:
  ```toml
  [profile.default]
  slow-timeout = { period = "30s", terminate-after = 4 }
  [profile.ci]
  fail-fast = false
  retries = 2
  [profile.ci.junit]
  path = "junit.xml"          # → target/nextest/ci/junit.xml
  ```
  Run `cargo nextest run --profile ci` in CI; install with `taiki-e/install-action` (`tool: nextest`). Flaky passes count as success by default; `flaky-result = "fail"` (≥0.9.131) makes them fail. Pitfall: nextest does not run doctests: add `cargo test --doc` if any exist. <https://nexte.st/docs/configuration/> <https://nexte.st/docs/machine-readable/junit/> <https://nexte.st/docs/features/retries/> <https://nexte.st/docs/features/slow-tests/>
- **OpenAPI drift**: simplest is a test that renders the spec and compares it to the committed `contracts/openapi.json` (print a "run `mise run contracts`" hint on mismatch). `insta::assert_json_snapshot!` is the richer alternative: `INSTA_UPDATE=auto` writes `.snap.new` locally and nothing in CI, so CI fails on drift. Pick one; the committed JSON file is also the codegen input, so the file comparison avoids a second copy. <https://insta.rs/docs/advanced/>

## 3. sqlx 0.9 + SQLite
- Options: `SqliteConnectOptions::from_str(url)?.create_if_missing(true).journal_mode(Wal).synchronous(Normal).busy_timeout(5s).foreign_keys(true)`, plus `.pragma("temp_store","memory")` if wanted. sqlx sets **no** journal mode by default (on purpose) and `synchronous` stays FULL unless set; `busy_timeout` default is 5 s, `foreign_keys` ON. <https://docs.rs/sqlx/0.9.0/sqlx/sqlite/struct.SqliteConnectOptions.html>
- `synchronous=NORMAL` in WAL is corruption-safe; a power loss can drop the last commits only. Fine for this data. <https://www.sqlite.org/pragma.html#pragma_synchronous> <https://www.sqlite.org/wal.html>
- Pool: `max_connections(4–8)` on 2 vCPU; WAL gives concurrent readers plus one writer. Write transactions that read first must start with `pool.begin_with("BEGIN IMMEDIATE")` (present in sqlx 0.9 `Pool::begin_with`): a deferred transaction that later upgrades to write gets `SQLITE_BUSY` immediately, without waiting on `busy_timeout`. Single-statement `UPDATE`/`INSERT` in autocommit are fine. <https://www.sqlite.org/lang_transaction.html>
- Migrations: `sqlx::migrate!("./migrations").run(&pool).await?` at boot. It embeds files at compile time and needs no `DATABASE_URL` (only `query!` macros do). Add `build.rs` with `println!("cargo:rerun-if-changed=migrations");` (or `sqlx migrate build-script`), otherwise a new migration file alone does not trigger a rebuild. <https://docs.rs/sqlx/0.9.0/sqlx/macro.migrate.html>
- JSON records: `analyses(id TEXT PRIMARY KEY, status TEXT, input_hash TEXT UNIQUE, created_at, updated_at, record TEXT NOT NULL)`; bind with `sqlx::types::Json<Analysis>` (the workspace enables the `json` feature). Keep fields you filter or sort on as real columns; never `json_extract` in hot paths.
- Pitfalls: mount the **directory** holding `app.db` in Docker, not the file: WAL needs the `-wal`/`-shm` siblings next to it. Do not set `journal_mode` differently on another connection or tool: switching out of WAL takes an exclusive lock (`database is locked`). Note the explicit sqlx docs comment on this in `SqliteConnectOptions::journal_mode`.

## 4. SSE progress stream
- Handler: on connect, `subscribe()` to the analysis' `broadcast::Sender` **first**, then load the record from SQLite and emit it as one `snapshot` event, then forward deltas, skipping any whose `seq` ≤ the snapshot's `seq`. Subscribe-then-read closes the gap where a step finishes between read and subscribe.
- Give every event `Event::default().id(seq.to_string()).event("step").json_data(..)`. On reconnect the browser sends `Last-Event-ID`; simplest correct handling is to always resend the snapshot (it is small) and let the client replace its state. `retry:` (`Event::retry`) sets the client's reconnect delay. <https://html.spec.whatwg.org/multipage/server-sent-events.html>
- `Sse::new(stream).keep_alive(KeepAlive::default())` (15 s comment ping in axum 0.8.9) keeps proxies and NAT from idling the connection. <https://docs.rs/axum/0.8.9/axum/response/sse/struct.KeepAlive.html>
- Lag: `BroadcastStream` yields `Err(BroadcastStreamRecvError::Lagged(n))`; the receiver stays usable. Treat lag as "resync": re-read the record and emit a fresh snapshot, never drop the error silently. Channel capacity 64 is plenty for ~10 steps. <https://docs.rs/tokio/1.54.1/tokio/sync/broadcast/index.html> <https://docs.rs/tokio-stream/latest/tokio_stream/wrappers/struct.BroadcastStream.html>
- End the stream after the terminal event (`done`/`failed`), and have the client call `es.close()` on it; otherwise `EventSource` reconnects forever and re-downloads the snapshot. For already-finished analyses, send snapshot + terminal event and close.
- Shutdown pitfall: `with_graceful_shutdown` waits for open SSE responses forever (axum #2673, closed as not planned). Wrap each SSE stream with `take_until(shutdown_token.cancelled_owned())` from a shared `CancellationToken`. <https://github.com/tokio-rs/axum/issues/2673>
- Caddy flushes `text/event-stream` responses immediately regardless of `flush_interval`, and `encode` does not hold SSE back for `minimum_length`. No proxy config needed. <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#streaming> <https://caddyserver.com/docs/caddyfile/directives/encode>
- Client: `EventSource` cannot set headers (fine, no auth); it gives up permanently on a non-200 or wrong content type, so return 404 as JSON before starting the stream and show a retry button on `error` with `readyState === CLOSED`. <https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events>

## 5. In-process jobs
- `POST /api/analyses`: insert row `queued` (dedupe on `input_hash` → return the existing id), then `tracker.spawn(run_job(state, id, token.child_token()))`. Inside, `Semaphore::acquire_owned()` around model stages only; external-API stages can overlap.
- Use `tokio_util::task::TaskTracker` + `CancellationToken` (the workspace already enables tokio-util `rt`): on shutdown `token.cancel(); tracker.close(); timeout(20s, tracker.wait())`. The TaskTracker docs recommend it over `JoinSet` for spawn-and-forget tasks because finished tasks free memory immediately and it is `Clone`. <https://docs.rs/tokio-util/0.7.20/tokio_util/task/task_tracker/struct.TaskTracker.html> <https://tokio.rs/tokio/topics/shutdown>
- Cancellation points: `tokio::select!` on `token.cancelled()` around each worker call; write `failed: cancelled` to the step so the record is never left `running`.
- Restart recovery at boot (before serving): `UPDATE analyses SET status='failed', … WHERE status IN ('queued','running')`, or re-enqueue `queued` ones. Docker's default `stop_grace_period` is 10 s, so keep the drain timeout below it or raise it in compose. <https://docs.docker.com/reference/compose-file/services/>
- Per-stage timeout: `reqwest::RequestBuilder::timeout(..)` per call (client-wide `.timeout` is a global cap). Set `pool_idle_timeout(Duration::from_secs(4))` on the client: reqwest keeps idle connections 90 s (0.13.5 source) while uvicorn closes them after 5 s (`--timeout-keep-alive` default), which produces sporadic `connection closed before message completed` on reuse. Retry a stage once only on connect errors. <https://github.com/encode/uvicorn/blob/main/docs/settings.md> <https://github.com/hyperium/hyper/issues/2136>
- When to use apalis (1.1.1, `apalis-sqlite` 1.1.0): durable retries/backoff, cron, multiple worker processes. None apply to one VPS and a 48 h demo; the SQLite row is already the durable state. <https://github.com/apalis-dev/apalis>

## 6. Rust → OpenAPI → pydantic / TypeScript contract
- utoipa 6 defaults to OpenAPI **3.1.0**; keep it. With utoipa-axum: `OpenApiRouter::with_openapi(ApiDoc::openapi()).routes(routes!(create, get_one))…split_for_parts()`; one binary/test dumps both `openapi.json` and `worker.openapi.json`.
- Field rules (utoipa-gen docs): a field is **required** unless it is `Option`, has `skip_serializing_if`, or `#[serde(default)]`; `Option` ⇒ nullable. So `#[serde(default)] steps: Vec<Step>` becomes optional (`steps?:` in TS) even though the server always sends it: add `#[schema(required = true)]` on response types. <https://docs.rs/utoipa/6.0.0/utoipa/derive.ToSchema.html>
- `#[serde(deny_unknown_fields)]` ⇒ `additionalProperties: false` (utoipa-gen `schema.rs`), which datamodel-code-generator turns into `model_config = ConfigDict(extra='forbid')`. Use it on `StagePatch` types (Rust rejects a worker sending fields it does not own). On `Analysis` sent *to* the worker, `extra='forbid'` means any new Rust field breaks the worker until codegen reruns: that is the drift alarm you want, as long as CI regenerates.
- Internally tagged enums (`#[serde(tag = "kind")]`) render as `oneOf` of objects with a single-value `kind` enum; utoipa emits a `discriminator` **only** for `#[serde(untagged)]` enums whose variants are single unnamed `ToSchema` refs (`enums.rs`). Without it pydantic tries variants in turn; error messages get noisy but parsing works. Prefer struct variants with distinct required fields, or the untagged + `#[schema(discriminator = "kind")]` form if you need real discriminated unions.
- serde pitfalls: `deny_unknown_fields` combined with `flatten` is unsatisfiable (serde #1358); `tag` + `deny_unknown_fields` on a plain struct cannot round-trip (serde #2666). Round-trip-test every variant against a fixture JSON. <https://github.com/serde-rs/serde/issues/1358> <https://github.com/serde-rs/serde/issues/2666>
- datamodel-code-generator 0.96: `datamodel-codegen --input contracts/worker.openapi.json --input-file-type openapi --output-model-type pydantic_v2.BaseModel --preset standard-py314-20261112 --output contracts/python/models.py`. Presets are dated and immutable, and the project ships behaviour changes only behind new options, so pin the version in `uv.lock` and the preset name. `--recommend-options` (experimental) suggests flags for your schema. <https://github.com/datamodel-code-generator/datamodel-code-generator/blob/main/docs/getting-started.md>
- openapi-typescript 7.13 reads 3.1 `type: [T, "null"]` as `T | null`; pair with `openapi-fetch`. <https://openapi-ts.dev/introduction>
- Integers: `u64`/`i64` become JSON numbers; JS loses precision above 2^53. Use `u32` for counts and strings for ids (`uuid` v7 already). Timestamps as RFC 3339 strings (`chrono` + utoipa `chrono` feature → `format: date-time`).
- Pitfall: utoipa-scalar 0.4 loads `https://cdn.jsdelivr.net/npm/@scalar/api-reference` unpinned (`res/scalar.html`). A CDN change can break `/api/docs` mid-demo and a strict CSP blocks it; pin via custom HTML or exempt `/api/docs` from CSP.

## 7. Per-IP rate limiting behind Caddy
- Caddy's `reverse_proxy` by default **ignores** incoming `X-Forwarded-*` from untrusted clients and sets `X-Forwarded-For` to the real peer IP; `trusted_proxies` is only for a CDN in front. So behind Caddy the leftmost XFF entry is trustworthy, **provided** the API port is reachable only through Caddy (no `ports:` on the `api` service). <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#defaults>
- `tower_governor 0.8` (axum ^0.8, governor ^0.10): `GovernorConfigBuilder::default().key_extractor(SmartIpKeyExtractor).per_second(..).burst_size(..).finish()`, applied with `.route_layer(GovernorLayer::new(conf))` on `POST /api/analyses` only, so `GET`s and SSE reconnects are not limited. `SmartIpKeyExtractor` reads XFF → X-Real-IP → Forwarded → peer IP (source `key_extractor.rs`). <https://docs.rs/tower_governor/0.8.0/tower_governor/>
- Serve with `app.into_make_service_with_connect_info::<SocketAddr>()` (needed for the peer-IP fallback), and prune state with `limiter.retain_recent()` on an interval as the README shows.
- Pitfalls: `default-features = false, features = ["axum"]` to avoid compiling tonic. Without Caddy in front (local dev, tests), every request has the same key or a spoofable XFF; set a test-only config. A hand-written `governor::RateLimiter::keyed` + `middleware::from_fn` is ~30 lines if the layer's 429 body format matters. <https://docs.rs/governor/0.10.4/governor/>

## 8. Docker images and CI publishing
- Rust (cargo-chef, official README pattern): `chef` (`lukemathwalker/cargo-chef:latest-rust-1`) → `planner` (`cargo chef prepare`) → `builder` (`cargo chef cook --release --recipe-path recipe.json`, then `COPY . .` and `cargo build --release -p api`) → `gcr.io/distroless/cc-debian13:nonroot`. Copy `rust-toolchain.toml` into the chef stage so the pinned 1.100.0 toolchain download is cached in a layer [inference: rustup honours the file inside the image]. <https://github.com/LukeMathWalker/cargo-chef>
- Why `distroless/cc`: bundled SQLite and rustls need only glibc + libgcc; no shell or package manager. `scratch` + musl adds a cross target, musl's slow allocator and no CA bundle for reqwest's webpki/native roots [unverified for 0.13's default root store]. debian-slim only if you need a shell for debugging (or use the `:debug` distroless tag, which has busybox). <https://github.com/GoogleContainerTools/distroless>
- Healthcheck without curl: add an `api healthcheck` subcommand that GETs `http://127.0.0.1:PORT/api/health` with reqwest and exits 0/1; compose `healthcheck: test: ["CMD", "/app/api", "healthcheck"]`. Worker: `["CMD", "python", "-c", "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]` with `start_period` covering model load. Then `depends_on: worker: condition: service_healthy`. <https://docs.docker.com/reference/compose-file/services/#healthcheck>
- `nonroot` runs as uid 65532: pre-create the SQLite volume directory owned by 65532 (or `user:` in compose) or the first write fails with `unable to open database file`.
- Python (uv guide): `FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim`, `ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1`, first `RUN --mount=type=cache,target=/root/.cache/uv --mount=type=bind,source=uv.lock,target=uv.lock --mount=type=bind,source=pyproject.toml,target=pyproject.toml uv sync --frozen --no-install-project`, then `COPY . .` and `uv sync --locked`. Bytecode compile cuts cold start; the cache mount keeps wheels out of the layer. <https://docs.astral.sh/uv/guides/integration/docker/>
- CPU-only torch: `[[tool.uv.index]] name="pytorch-cpu" url="https://download.pytorch.org/whl/cpu" explicit=true` and `[tool.uv.sources] torch = [{ index = "pytorch-cpu" }]`. `explicit = true` keeps the index from serving other packages. Without it, Linux resolves the default PyPI wheel that pulls CUDA libraries (several GB). <https://docs.astral.sh/uv/guides/integration/pytorch/>
- GHCR in Actions: `permissions: { contents: read, packages: write }`, `docker/login-action@v4` with `GITHUB_TOKEN`, `docker/metadata-action@v6` (tags `sha-<short>` + `latest`), `docker/setup-buildx-action@v4`, `docker/build-push-action@v7` with `cache-from: type=gha,scope=api` / `cache-to: type=gha,mode=max,scope=api` (and `scope=worker`). Without distinct `scope`s the two images overwrite each other's cache. <https://docs.docker.com/build/ci/github-actions/cache/> <https://docs.docker.com/build/cache/backends/gha/>
- Pitfall: `RUN --mount=type=cache` contents are **not** exported to the gha cache; in CI the cargo-chef `cook` layer is what gets cached, so keep it. GitHub's cache is size-limited and evicts on inactivity; the first build of the day can be cold.

## 9. Git hooks (mixed Rust/Python)
- Keep the existing plain-shell `.githooks/` (set by `mise run setup`); adding lefthook or the pre-commit framework would be a second convention. Extend `pre-commit` with a guarded format check:
  ```sh
  rs=$(git diff --cached --name-only --diff-filter=ACMR -- '*.rs')
  [ -n "$rs" ] && for f in $rs; do git show ":$f" | rustfmt --edition 2024 --check >/dev/null || { echo "rustfmt: $f"; exit 1; }; done
  ```
  Reading `git show ":$f"` checks the **staged** blob, not the working tree.
- Clippy (and `cargo fmt --check`) compile/read the working tree, not the index, so a hook can pass on unstaged edits and fail on what you commit, or vice versa. Put `cargo clippy --workspace --all-targets -- -D warnings` in `pre-push` (tree usually clean) guarded by `git diff --name-only @{u}.. -- '*.rs' Cargo.toml Cargo.lock`, and let CI be the real gate. Avoid `git stash --keep-index` in hooks: it can lose work on conflicts. <https://stackoverflow.com/questions/20479794/how-do-i-properly-git-stash-pop-in-pre-commit-hooks-to-get-a-clean-working-tree>
- If you ever switch: the pre-commit framework stashes unstaged changes before running hooks (so clippy would see the index) but needs Python; lefthook 2.x filters by `glob` and can re-stage fixes with `stage_fixed: true` (pre-commit only). <https://pre-commit.com/> <https://lefthook.dev/configuration/stage_fixed.html>

## 10. FastAPI worker for CPU inference
- **One uvicorn process** (`--workers 1`, the default): models load once, GDELT limiter stays process-global. Load models in `lifespan` (`@asynccontextmanager`, yield, then release), store on `app.state`; `/health` returns 503 until loaded and lists loaded models. <https://fastapi.tiangolo.com/advanced/events/>
- Stage endpoints doing CPU work are plain `def` (FastAPI runs them in the AnyIO threadpool, default 40 tokens); `/health` is `async def` and does no work. Measured in `plans/backend-approaches.md`: CPU work inside `async def` froze `/health` for 2.9 s. <https://fastapi.tiangolo.com/async/> <https://anyio.readthedocs.io/en/stable/threads.html>
- Serialise model inference: a module-level `threading.Lock` per model (or one for all) even though Rust holds `Semaphore(1)`. Two concurrent torch calls each using all intra-op threads oversubscribe 2 vCPUs and run slower than sequentially.
- Threads: `torch.set_num_threads(2)`, `torch.set_num_interop_threads(1)` at startup (interop must be set before any parallel work), plus `OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false` in the compose env. Wrap inference in `torch.inference_mode()`. <https://docs.pytorch.org/docs/stable/threading_environment_variables.html> <https://docs.pytorch.org/docs/stable/notes/cpu_threading_torchscript_inference.html>
- Memory on 8 GB: ONNX Runtime **dynamic int8** (`onnxruntime.quantization.quantize_dynamic(..., weight_type=QuantType.QInt8)`) shrinks MatMul and `Gather` (embeddings; `Gather` is in ORT's common op registry) weights ~4×: the 2.2 GB XLM-R large becomes roughly 0.6 GB [estimate]. Validate accuracy on the eval set before switching; ORT warns dynamic quant can be slow on CPUs without VNNI. Export path: `optimum-onnx` (0.1.0, the ONNX half split out of optimum 2.x) [unverified API]. <https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html> <https://huggingface.co/docs/optimum-onnx/onnxruntime/usage_guides/quantization>
- Set `mem_limit` on the worker (e.g. 6g) so an OOM kills the worker (Docker restarts it, API marks the step failed) instead of the kernel choosing the API or Caddy. Run one warm-up inference at startup; first calls are slower.
- Runtime: `HF_HOME=/models` on the `hf-cache` volume and `HF_HUB_OFFLINE=1` so a missing model fails at boot, not by downloading during the demo.

## 11. Caddy 2 in Compose
- Compose: `caddy:2` image, `ports: ["80:80", "443:443", "443:443/udp"]`, named volumes `caddy_data:/data` (certificates + ACME account) and `caddy_config:/config`, `./deploy/Caddyfile:/etc/caddy/Caddyfile:ro`, `./web/dist:/srv:ro`. Losing `/data` re-issues certs and can hit Let's Encrypt rate limits. <https://hub.docker.com/_/caddy>
- Caddyfile (official SPA pattern):
  ```caddy
  {$SITE_HOST} {
  	encode zstd gzip
  	header {
  		Strict-Transport-Security "max-age=31536000"
  		X-Content-Type-Options nosniff
  		Referrer-Policy strict-origin-when-cross-origin
  		-Server
  	}
  	handle /api/* {
  		reverse_proxy api:8080
  	}
  	handle {
  		root * /srv
  		route {
  			try_files {path} /index.html
  			header /index.html Cache-Control "no-cache"
  		}
  		file_server
  	}
  }
  ```
  `handle` blocks are mutually exclusive, so `/api/*` never falls through to `index.html`. <https://caddyserver.com/docs/caddyfile/patterns#single-page-apps-spas> <https://caddyserver.com/docs/caddyfile/directives/header>
- Automatic HTTPS needs the hostname's public DNS pointing at the VPS and 80/443 open before first start (`srvNNNNNN.hstgr.cloud` resolves publicly [unverified for our VPS]). Test once with the staging CA (`acme_ca https://acme-staging-v02.api.letsencrypt.org/directory`) if you will recreate volumes repeatedly.
- Pitfall: a Caddy config reload closes long-lived streams (documented for WebSockets; `stream_close_delay` delays it) [unverified for SSE]. EventSource reconnects and §4's snapshot-on-connect makes this harmless. Never reload Caddy mid-demo anyway. <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#streaming>

## 12. Demo-day hardening
- **Golden replays**: seed 3–5 finished analyses (fixture JSON in `evals/fixtures/`) and serve them through the same SSE path with a `?replay=1` mode that re-emits stored steps with short delays. The live demo then never depends on GDELT/LLM/model latency; dedupe-by-hash makes re-submitting a seeded input instant.
- **Feature flags via env** (no framework): `STAGES_DISABLED=signals_coord,retrieve` makes the orchestrator mark a step `skipped` with a reason, and the score abstains as designed. Flip with `docker compose up -d` and no rebuild.
- **Rollback**: tag images `sha-<short>` (metadata-action) and reference `${API_TAG}`/`${WORKER_TAG}` in compose; rollback is one env change + `docker compose up -d`. Freeze deploys an hour before judging.
- **Backups**: a tokio interval task in the API runs `VACUUM INTO '/data/backup/app-<ts>.db'` every 15 min (consistent snapshot while running, no `sqlite3` binary needed in distroless) and keeps the last N. Litestream 0.5.18 streams the WAL to S3 if you want off-box copies. <https://www.sqlite.org/lang_vacuum.html#vacuuminto> <https://litestream.io/>
- **Observability**: JSON logs (`tracing-subscriber` `json` feature, already enabled) with `request_id` + `analysis_id` span fields on both sides; `docker compose logs -f api worker | grep <id>` is the debugger. `/api/health` checks DB (`SELECT 1`) and worker `/health`; an external uptime ping on it pages the team [optional].
- **VPS**: 4 GB swap, `restart: unless-stopped` on all services, firewall 22/80/443 only, `docker login ghcr.io` with a read-only PAT while the repo is private. <https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry>

## Priorities

### Adopt now
1. lib + thin main, `app()`/`serve()` shared by tests; `ApiError` with JSON body; request-id → trace → propagate; `TimeoutLayer::with_status_code`; explicit body limit.
2. SQLite: WAL + NORMAL + busy_timeout + `BEGIN IMMEDIATE` for read-then-write; `migrate!` + `build.rs`; tempfile DB per test.
3. Real-server tests on `127.0.0.1:0` with wiremock per test; nextest `ci` profile with JUnit.
4. SSE: subscribe-then-snapshot, `id:` per event, keep-alive, lag → resync, close on terminal event, `take_until(cancel)` for shutdown.
5. `TaskTracker` + `CancellationToken`; boot-time `running → failed`; per-stage reqwest timeouts; `pool_idle_timeout(4s)`.
6. Contract: OpenAPI 3.1, `required = true` on always-present fields, drift test against `contracts/openapi.json`, pinned datamodel-codegen preset.
7. Worker: one process, `lifespan` loading, `def` stage endpoints + inference lock, torch threads = 2, `HF_HUB_OFFLINE=1`, `mem_limit`.
8. Images: cargo-chef → `distroless/cc-debian13:nonroot`; uv `python3.14-trixie-slim` with cache mounts and CPU torch index; gha cache with per-image `scope`; binary-based healthchecks.
9. Caddy SPA + `/api` proxy, persistent `/data`, API port unpublished; `tower_governor` on `POST /api/analyses` only.
10. Golden replays and `sha-` image tags for rollback.

### Later if time
- ONNX int8 quantisation (after eval-set comparison), warm-up inference.
- `VACUUM INTO` backup task or Litestream.
- Staged-blob rustfmt in `pre-commit`, clippy in `pre-push`.
- insta snapshots, `axum-test`, `flaky-result = "fail"`.
- Pinned Scalar asset + CSP header.
- `STAGES_DISABLED` flags beyond the stages that actually flake.

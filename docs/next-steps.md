# Next steps (Sat 20:30 round)

Living task list per person, kept by the integrator. Agents: read your section, `AGENTS.md` and `DECISIONS.md` first; do only what is listed for your owner; ask the integrator before touching a folder you do not own. Lyreplus's detailed requests per person are in `docs/ai-core.md` → "Requests to the team".

## State of `main` (Sat 20:30)
- Live at <https://the4thlover.tech> (API docs: `/api/docs`). Every merge to `main` deploys; the deploy goes red if a stage fails to import.
- **All stages are on `main`** and run end to end on the VPS: `extract`, `understand`, `retrieve`, `story`, `signals_single`, `signals_coordinated`, `score`, `explain`.
- Merged since the 16:30 round: #15 signals on real coverage; #16 `retrieve` + `story`; #17 AI-core requests; #18 fact-check adapter (D8), exact-phrase search, ~300 typed outlets, story threshold 0.90 / 0.845; #20 `OutletType::Satire`, fixture technique scale; #21 + #24 **no Chromium: Oxylabs AI Studio** reads blocked pages and searches the web (phrases and news), Playwright removed; #22 labelled set 284 items (en 57, es 54, de 51, it 43, fr 41, nl 18); #23 metrics with coverage, `n/a` and the headline with/without the label's own source; #26 demo analysis IDs and submission text (`docs/pitch/`); #27 AI core: satire guard (single-actor abstains on a satire outlet, `outlet_satire` = -1.0, satire is never a copier or a tone/claim peer), cross-lingual fact-check verdict match (`fcd_de_002`: abstain → single 0.832 via Climate Feedback found by `oxylabs_news`), zero-evidence baseline kept and explained, `known_networks` also counts listed same-story outlets.
- **Oxylabs works on the VPS** (`OXYLABS_TOKEN` set). **The Google Fact Check key is not set yet**: until it is, retrieve finds no fact-checks and the `fact_checks` family is empty.
- **`web/` v1 is on `main`** (#31, mosearc): `/` with the 5 demo presets (`web/src/data/presets.ts`, replay links), `/analyses/{id}`, `/metrics`. Still missing: **no `evals/metrics.json`** (`/api/metrics` is 404, the page says "metrics coming"); `pipeline/score/weights.json` is still priors (`n = 0`), so the explanation says the confidences are uncalibrated.

### Live runs on the VPS (Sat 18:20, `sha-151a062`)
Use them with `GET /api/analyses/{id}` or `rerun?from=<stage>`.

| Input | ID | extract | retrieve | Context | Scores |
|---|---|---|---|---|---|
| France24 URL (DR Congo / Rwanda) | `01a1dadf-ac1c-77ec-9cd9-8b3ccb9efbf6` | 30 s, 9 paragraphs | 12 s | `oxylabs` 1, `oxylabs_news` 1 | both abstain: too few reports |
| ANSA URL (Duffy, air traffic) | `01a1dadf-ae67-7207-a174-62efae9b62ba` | 0 s | 48 s | `feeds` 3, `oxylabs` 1, `oxylabs_news` 1; 3 of 5 in story | single 0.076, coordinated 0.076 |
| Pasted Tylenol–autism claim | `01a1dae0-e28e-71e1-b0dd-12fb920f41cd` | 0 s | 42 s | `oxylabs_news` 2; 0 of 2 in story | both abstain; no fact-check (no key) |

## Critical path
```mermaid
flowchart LR
  KEY[Degra02: fact-check key on VPS] --> RUN[Degra02: eval run, 284 items]
  RUN -->|fit.jsonl| FIT[Lyreplus: fit weights.json]
  RUN -->|predictions.jsonl| MET[mosearc: metrics.json]
  FIT --> MET
  FE[ck-lithium: web/ v1] --> DEMO[mosearc: demo IDs + video]
  MET --> DEMO
```

## Deadlines
| When | What |
|---|---|
| ~~Sat 18:00~~ partly missed | MVP green: retrieve + story live (done); **frontend v1, real metrics, demo IDs still open** |
| Sun 03:00 | Feature freeze |
| Sun 09:00 | Submission: video, description, repo public under MIT |

## Rules for every agent
- Own branch `<person>/<topic>`, rebased on `main`; PR every ~2 h; `mise run check` passes before asking for a merge. **Work pushed after a PR is merged does not reach `main`: open a new PR.** Merged branches are deleted on GitHub; start the next piece of work from a fresh branch off `main`.
- A dependency is `uv add <pkg>` on your branch; say in the PR why, and its size if it is large (the worker image and the VPS have 2 vCPU / 8 GB, worker limit 6 GB).
- Contract changes (`contracts/`), `pyproject.toml` conflicts, `mise.toml`, CI, `deploy/`, `README.md`, `docs/plan.md`: ask the integrator.
- Test a stage alone with `pipeline.common.fixtures.example_analysis()`; iterate on a finished analysis with `POST /api/analyses/{id}/rerun?from=<stage>`.
- Never commit secrets, scraped article text or downloaded datasets (`evals/data/` is gitignored).

## ck-lithium — `web/` is yours from here
Retrieve, story and the Oxylabs cutover are merged. Retrieve on the VPS: an Italian ANSA article got 5 context items from 5 outlets in 48 s (task 2 of the last round: done for Italian).
1. **Frontend v1 merged (#31, built by mosearc).** `mise run web:dev` (`VITE_API_TARGET=https://the4thlover.tech` for live data); handoff notes in `web/README.md`. Check the result page on the live runs and fix what reads badly; no "propaganda / not" label (D4).
2. **Satire sites**: `ck-lithium/satire` has the `outlets.json` list (commit 16:39) but no PR: open it. Since #27 a satire outlet makes the single-actor score abstain ("The source is a satire publication…"), so the list is what turns the guard on.
3. **France24 extract took 30 s** on the VPS although it answers plain HTTP from a laptop: probably the VPS address is refused and the page went through Oxylabs. Check the worker log when you can; fine if that is the case.
4. **After the fact-check key is set** (integrator): `fcd_*` items get a context item with `fact_check` and a `fact_checks / rated_*` evidence item; `registered_at` filled for ansa.it, tagesschau.de, rte.ie.
   - **Pravda sister sites** (`pk_*` items get no copies on the network's other editions; their `/rss.xml` feeds are the way): **wait for Lyreplus task 1 before adding listed-network feeds.** Since #27 `known_networks` counts any listed outlet in the document's story; with those feeds in retrieve, mainstream articles on events the network also covers would score coordinated 0.622.
5. Small: `pipeline/extract/tests/test_live.py:130` still mentions `OXYLABS_USERNAME` / `OXYLABS_PASSWORD`; only `OXYLABS_TOKEN` is read.

## Lyreplus — AI core on real data
All AI-core stages are done on `main`. #27 closed the 18:30 items on the zero-evidence baseline, speed (VPS: `signals_single` p50 3.1 s / p95 33 s, analysis p50 22 s / p95 66 s) and satire.
1. **Guard the story path of `known_networks` (#27) before ck-lithium adds Pravda feeds.** `known_network_evidence` now lists any `in_story` outlet on a documented network, but `in_story` means same event, not same text. Repro (integrator, Sat 20:20): the live ANSA record `01a1dadf-ae67-…` with one in-story outlet (`tg24.sky.it`) marked `known_network = portal_kombat` scores coordinated **0.622** on #27 and 0.076 on the code before it, the same as a real Pravda article, with "Another site covering the story is on a published list…". No live record is affected today (none of the 8 known runs has a listed outlet in its story). Suggested guard: count same-story listed outlets only when the document has no outlet (pasted text) or its outlet is not one of `_NOT_COPIERS` (wire, national, local, fact-checker, satire); or require a near-duplicate similarity, not the story threshold. Add a test with a mainstream document and a listed same-story peer.
2. **Fit the combiner** as soon as the integrator hands over `evals/results/fit.jsonl` (blocked on the eval run, which waits for the fact-check key so `fact_checks` is not empty): `python -m pipeline.score.fit evals/results/fit.jsonl`, commit `weights.json` with its `cv` block. Tell mosearc when it is merged so the metrics are recomputed (#23 reads `weights.json → cv` for the headline).
3. **Signals vs real retrieve output**, with ck-lithium: `in_story` under 0.90 / 0.845 (the Tylenol run had 0 of 2 in story, ANSA 3 of 5), `wire_service` outlets, the new `oxylabs` / `oxylabs_news` items, fact-check items once the key is set.
4. Re-run the demo items with `rerun?from=signals_single` after each signal or weight change and compare with mosearc.

## mosearc — evaluation, metrics, pitch
`metrics.py` coverage / `n/a` / headline (#23), the labelled-set gaps (#22) and the demo IDs with the submission text (#26) are merged: done.
1. **Demo after #27**: `fcd_de_002` should now score single-actor (0.832 in Lyreplus's VPS test) without the fact-check key. After the #27 deploy, `POST /api/analyses/01a1daeb-b551-7706-ae2b-6ad7f0540212/rerun?from=signals_single`, put the new ID in `docs/pitch/demo-script.md` and give the single-actor beat back its evidence instead of the abstention. Re-check `fc_de_005` (the BR24 debunk) stays low the same way. Re-submit the `fcd_*` items once more after the fact-check key is set.
   - Open questions from #26 for the team: the project name (not in the repo) and whether to claim Google MLH "Best Use of Gemini API" (no grounded-search adapter; the LLM is `gemini-3.1-flash-lite` via AI Router).
2. **Metrics** (blocked on the integrator's eval run, then on Lyreplus's fit): `mise run eval -- eval evals/results/predictions.jsonl --json evals/metrics.json` and commit `evals/metrics.json` (numbers only). Recompute after the fit lands.
3. **Pitch** (`docs/pitch/`): demo script final now (metrics beat once the numbers exist); video, description and submission text before Sun 09:00. The live runs above show the abstention path ("not enough evidence") honestly: worth a beat.

## Integrator (Degra02)
1. **Google Fact Check key** (blocks the eval run): Google Cloud → enable "Fact Check Tools API" → Credentials → API key, restricted to that API. Put `GOOGLE_FACTCHECK_API_KEY` in the VPS `.env`, `docker compose --env-file .env --env-file release.env up -d --force-recreate worker`, check with a `claims:search` call from the container, then re-run the Tylenol test.
2. **Eval run** (284 items; blocks Lyreplus and mosearc) after the key. The API has no host port on the VPS and the VPS has no checkout, so the runner runs from a laptop: against a local API with the limits off (`deploy/README.md`, "Local"), or `--api https://the4thlover.tech --concurrency 2` (stays under 30/min and 600/h, but the site is busy for hours). `fit.jsonl` → Lyreplus, `predictions.jsonl` → mosearc.
3. **Memory**: `docker stats --no-stream` on the VPS during an analysis; post the worker number (limit 6 GB). ck-lithium cannot reach the VPS shell.
4. **Decision still open**: whether `claim_support` gets an LLM verifier per (claim, passage) for false NLI contradictions (network I/O in a signal stage, beyond D5) or the fit decides its weight.
5. `k8s` branch: 3 commits ahead of `main` (latest: "build docker images on k8s branch"), no PR; Kubernetes is not in `docs/plan.md`. Merge or drop.
6. Keep `main` deployable; update this file after every round.

## Source graph (Sun 00:25): phase 0 is on `main`
**What it is.** The analyses we store also show which outlets are tied to each other, and by what evidence. `pipeline/graph/` (owner: Lyreplus) builds that graph offline from stored analyses; `evals/graph.json` is its output on the 277 eval records and `GET /api/graph` serves it. Research, model and results: `plans/source-graph.md`. Read its sections 3 to 5 before a graph task.

**Decided** (`DECISIONS.md`, Sun 00:25): phase 0 is merged; Lyreplus owns `pipeline/graph/`; one shared analytics ID is enough to join a cluster, for now. **Not decided**: a per-outlet track record (D4, D9). Do not build or show one.

**Priority.** Your tasks in the sections above come first. A task marked *now* is small, changes no contract and is safe before the Sun 03:00 freeze. A task marked *after submission* waits for Sun 09:00; *needs X* also waits for task X.

### Rules for every graph task
1. **No graph value in the score.** Do not add a graph signal to `pipeline/score/families.py` or `weights.json` before task L4 delivers a fit with its ablation. The calibrated numbers on the 284-item set must not move.
2. **A tie is evidence that two sites are related, not a judgement of either.** No label on an outlet anywhere (code, UI, docs, pitch): not "propaganda network", not "unreliable". Write "tied by", "same analytics ID", "same text" (D4).
3. **Covering the same topic is never a tie.** Only the layers in `COORDINATION` (`pipeline/graph/build.py`) count as coordination: `analytics_id`, `ad_account`, `copy`, `translation`.
4. **`evals/graph.json` is generated: never edit it by hand.** Rebuild with `mise run graph:build -- evals/results/fit.jsonl --labelled evals/labelled.jsonl` (about 2 minutes) and commit the file. `evals/results/fit.jsonl` is gitignored: ask Degra02 or Lyreplus for it.
5. **The shape of `GET /api/graph`** is the "Output" paragraph in the docstring of `pipeline/graph/build.py`. If you change a field, update that paragraph and name ck-lithium in the PR.
6. **Tests**: `uv run --frozen pytest pipeline/graph` (no network, no model). A new tie rule comes with a test in `pipeline/graph/tests/test_build.py`, built like the ones there (`article`, `corpus_of`, `found`).
7. **Contract changes are the integrator's**: a new stage, `Family`, `OutletType` or field in `contracts/`. Ask; do not edit.

### Degra02
| ID | When | Files | Do | Done when |
|---|---|---|---|---|
| D1 | now | — | After the deploy of the merge, check the live route. | `GET https://the4thlover.tech/api/graph` answers 200 and `counts.outlets` is 739. |
| D2 | after submission | `contracts/src/stage.rs`, `contracts/src/apply.rs`, `api/src/pipeline.rs`, `api/migrations/0003_graph.sql`, `api/src/graph.rs`, `api/src/routes/graph.rs` | Live ingestion (plan phase 1). `StageName::Graph` and `GraphPatch` (articles, ties with their evidence, tracking IDs), scheduled in the same group as `explain`. Tables for articles, outlets, IDs and ties; one transaction per analysis; rows keyed by article URL so a re-run updates instead of adding. `GET /api/graph` reads the tables and keeps the shape of `evals/graph.json`. `GET /api/graph/outlets/{domain}`. A command that replays stored analyses through the stage. | A new analysis adds its outlets to `GET /api/graph`; running the same input twice changes no count; a failed `graph` step does not stop `Db::find_reusable` from reusing the result; `mise run check` passes. |
| D3 | after submission, needs D2 | `api/src/routes/`, `contracts/src/stage.rs`, `contracts/src/analysis.rs`, `deploy/compose.yaml` | Memory (plan phase 2). `POST /internal/graph/recall`: nearest stored articles by cosine over their embeddings, and what the graph knows about a list of domains. Outside `/api/`, so Caddy does not expose it. `StageName::Recall` after `retrieve`; `analysis.graph`; memory items enter `context[]` with `retrieved_by: "memory"`; `GRAPH_API_URL=http://api:8080` for the worker. | `rerun?from=recall` refreshes the graph knowledge of a stored analysis without any web request. |
| D4 | when asked | `contracts/src/analysis.rs` | `OutletType::Official` and `OutletType::Aggregator` for C5; `Family::TrackRecord` and `Family::LinkedSources` for L4, only once its fit exists. | `mise run contracts` output committed. |

### Lyreplus (owner of `pipeline/graph/`)
| ID | When | Files | Do | Done when |
|---|---|---|---|---|
| L1 | now | `pipeline/signals/coordinated.py`, `pipeline/graph/build.py` | Read `LAYERS`, `republishes` and `copy_ties` against your rules in `coordinated.py`. `build.py` imports your private `_NOT_COPIERS`: rename it `NOT_COPIERS` and update the import. Write in the PR which prior ($\tau$, $q$ in `LAYERS`) you would change and why; do not change one without a rebuild (rule 4). | `rg _NOT_COPIERS pipeline` finds nothing; `uv run --frozen pytest pipeline/graph pipeline/signals` passes. |
| L2 | after submission, needs D2 | `pipeline/graph/__init__.py`, `pipeline/graph/build.py` | `run(analysis) -> GraphPatch`: the ties of one record, with the same rules as `build.ties` (its articles, their IDs, the embedding of `story_text` for each). Plain `def`, no network. Reuse the tie functions; do not copy them. | The stage on `example_analysis()` returns the analytics-ID tie between `daily-truth.example` and `free-nation-news.example`; a test covers it. |
| L3 | after submission, needs D3 | `pipeline/graph/recall.py` | `recall(analysis)`: embed the document, call the internal route, return the memory items and the graph profile of each outlet in `sources[]`. Then re-run the `pk_*` items of the labelled set. | A Pravda article whose translation on another edition was analysed before gets that edition as a context item, and coordinated evidence that does not come from `known_networks`. Report the coordinated CV AUC without `known_networks` (0.3751 today). |
| L4 | after submission, needs L3, D4 and M3 | `pipeline/signals/`, `pipeline/score/families.py`, `pipeline/score/fit.py`, `weights.json` | Family `linked_sources` (plan sections 4 and 6): the document's outlet is strongly tied to a listed outlet; value shrunk by $Z = n/(n+k)$; fit with `cv.ablation`. Family `track_record` is blocked until the team decides it (see "Not decided"); when it is, its outcomes use the confidence without the graph families. | AUC and FPR per hard-negative set with and without the family, evaluated in time order (M4); no hard-negative FPR gets worse. |
| L5 | after submission, needs L3 | `pipeline/signals/text.py` (`story_peers`), `pipeline/signals/claims.py` | A peer tied to the document's outlet (coordination ≥ 0.5 in `analysis.graph`) is not an independent source: leave it out of `claim_support` and `tone`. | The `eud_ru_002` and `eud_ru_005` false negatives (`docs/ai-core.md`) no longer get a negative `claim_support` from aligned outlets. |

### ck-lithium
| ID | When | Files | Do | Done when |
|---|---|---|---|---|
| C1 | now | `pipeline/retrieve/articles.py` (`context_item`, line 126), `pipeline/retrieve/__init__.py` (`fact_check_item`, line 180) | `context[].language` is taken from the page or the query. In the eval records it disagrees with the text for 160 of 1,657 items (52 labelled `it` are English; 96 labelled `en` are Spanish, French, German, Dutch, Italian or Russian). Set it from the item's text with `pipeline.extract.language.detect_language` (CPU-bound: from a thread in async code), keeping the old value only when nothing is detected. `story.threshold_for` picks its threshold from this field. Independent of the graph. | A test with an English text under a feed tagged `it` yields `language == "en"`; `uv run --frozen pytest pipeline/retrieve pipeline/story` passes. |
| C2 | now | `pipeline/retrieve/outlets.json` | The graph ties `rtrunews.com` to `rt-english.com` (same analytics ID `G-WSRRLSJZ2D`) and `esrt.press` to `actualidad-rt.com` (same ID, same text, links to `cdn.rt.com`); `de-rt.com` links to `rtd.rt.com`. Open each site; add the ones that are RT mirrors under `state_affiliated` (`rt.com` is already there). | `eud_en_002` (`rtrunews.com`, a false negative in `docs/ai-core.md` with `source_profile = 0`) gets `outlet_state_affiliated` after `rerun?from=retrieve`. |
| C3 | after submission | `pipeline/retrieve/outlets.json`, `pipeline/retrieve/registry.py` | Feeds (`/rss.xml`) of the `news-pravda.com` editions and of the `topwar.ru` language editions: four Pravda editions carry `topwar.ru` articles word for word. | Rebuilding the graph on new analyses of `pk_*` items shows more than one shared article per edition pair. |
| C4 | after submission | `web/src/pages/`, `web/src/lib/api.ts` | A `/sources` page on `GET /api/graph`: the clusters with what joins them (`joined_by`), and for an outlet its ties with the layer, the count and links to the evidence. Tables first; the map later. Rules 2 and 5 apply: no label on an outlet, a line saying a tie is evidence of a relationship and not a judgement, and how to ask for a correction. No track record. | `mise run web:build` passes; the page shows the cluster of `abc4.com`, `kxan.com`, `nbc4i.com`, `thehill.com` with "same analytics ID". |
| C5 | after submission, needs D4 | `pipeline/retrieve/outlets.json` | Official sites the host labels miss (`elysee.fr`, `boe.es`, `governo.it`, `bundesregierung.de`) and aggregators (`headtopics.com`). | They carry the new types; `pipeline/graph/build.py: republishes` reads the type. |

### mosearc
| ID | When | Files | Do | Done when |
|---|---|---|---|---|
| M1 | now | `docs/pitch/demo-script.md`, `docs/pitch/submission.md` | One beat and the "what's next" from plan section 3. Safe to say: the analyses we store also give a map of which sites are tied and by what evidence (built offline today; feeding it from every analysis is the next step); on 277 analyses no strong text tie came from the hard negatives; RT mirror domains found by a shared analytics ID; four Pravda editions carrying `topwar.ru` articles word for word. Say the limit: on content alone the listed network does not cluster yet. Rule 2 for the wording. | The beat is in the script with these numbers and no label on an outlet. |
| M2 | now or after submission | new `evals/graph_pairs.jsonl` | Hand-check the 22 strong ties between different operators: in `evals/graph.json`, the `edges` with `coordination >= 0.5` and no `same_operator` layer. Start with the 3 unverified ones: `andaluciainformacion.es` / `elconfidencialdigital.com` / `eldiariodemadrid.es`, `elperiodico.com` / `noticiasdenavarra.com`, `factchequeado.com` / `kunr.org`. One line per pair: `{"a", "b", "same_operator": true or false or null, "source": "<URL that shows the owner>", "note"}`. | 22 lines; the share with `same_operator: true` and its Wilson interval reported in the PR. |
| M3 | after submission | `evals/graph_pairs.jsonl` | Add the pairs to fit the layer weights: positives are pairs with a documented common operator (VIGINUM editions, the owners verified in M2); negatives are pairs of typed mainstream outlets of different owners, and the pairs behind the 33 weak ties from hard negatives (`evaluation.text_ties_from_hard_negatives_only`). | At least 50 positive and 50 negative pairs, each with a source. |
| M4 | after submission | `evals/src/propaganda_eval/` | The `evaluation` block of `/api/graph` on the metrics page. For L4: an evaluation in time order (items by `created_at`, the graph holds only earlier items, grouped by registrable domain). | The metrics page shows the two graph numbers (listed outlets clustered with and without the shared domain; strong text ties from hard negatives). |
| M5 | after submission | `SPEC.md` | A "Source map" section for what is built: ties with their evidence, clusters, no labels. Nothing about a track record until it is decided. | Section merged. |

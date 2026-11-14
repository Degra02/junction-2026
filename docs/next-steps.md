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

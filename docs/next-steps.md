# Next steps (Sat 15:00 round)

Living task list per person, kept by the integrator. Agents: read your section, `AGENTS.md` and `DECISIONS.md` first; do only what is listed for your owner; ask the integrator before touching a folder you do not own.

## State of `main` (Sat 15:00)
- Live at <https://the4thlover.tech> (API docs: `/api/docs`). Every merge to `main` deploys; the deploy goes red if a stage fails to import.
- Stages on `main`: `extract` (text and URL input, language with support tier), `understand`, `signals_single`, `signals_coordinated`, `score`, `explain`. Missing: `retrieve`, `story`.
- Without `retrieve`, every analysis has no context: `score` abstains ("not enough evidence") and coordinated signals stay empty. **`retrieve` is the critical path.**
- Eval harness in `evals/` (`mise run eval -- validate|stats|eval <predictions.jsonl>`); the labelled set has 10 synthetic seed items only.

## Deadlines
| When | What |
|---|---|
| Sat 16:00 | Real pasted text through the full pipeline on the VPS, with Google News context |
| Sat 18:00 | MVP green: all retrieval adapters, story clustering, frontend v1, first real metrics |
| Sun 03:00 | Feature freeze |
| Sun 09:00 | Submission: video, description, repo public under MIT |

## Rules for every agent
- Own branch `<person>/<topic>`, rebased on `main`; PR every ~2 h; `mise run check` passes before asking for a merge.
- A dependency is `uv add <pkg>` on your branch; say in the PR why, and its size if it is large (the worker image and the VPS have 2 vCPU / 8 GB, worker limit 6 GB).
- Contract changes (`contracts/`), `pyproject.toml` conflicts, `mise.toml`, CI, `deploy/`, `README.md`, `docs/plan.md`: ask the integrator.
- Test a stage alone with `pipeline.common.fixtures.example_analysis()`; iterate on a finished analysis with `POST /api/analyses/{id}/rerun?from=<stage>`.
- Never commit secrets, scraped article text or downloaded datasets (`evals/data/` is gitignored).

## ck-lithium — retrieve, story, then the frontend
1. **`retrieve`** (`pipeline/retrieve/__init__.py: async def run(analysis) -> RetrievePatch`). First version by 16:00 with Google News RSS only, then add adapters.
   - Queries: `analysis.queries` (from `understand`, in the item's language and English); Google News edition (`hl`, `gl`, `ceid`) from `analysis.language`.
   - Fetch the top 15–30 hits with `pipeline.extract.fetch` (every redirect hop is checked) and extract them with `pipeline.extract.article`. `context[].text` is the **full body**, never the RSS snippet: claim support and copy detection read it. Fill `outlet` (domain), `published_at`, `title`, `language`, `retrieved_by`, `tracking_ids`.
   - `sources[]`: one profile per domain for the **document's outlet and every context outlet**: `registered_at` (RDAP), `first_cert_at` (crt.sh), `outlet_type` (`wire_service` for agencies: Reuters, AP, AFP, dpa, EFE, ANSA… — the syndication guard depends on it), `country`, `known_network = "portal_kombat"` for VIGINUM-listed domains. The VIGINUM CSV writes domains defanged (`pravda-de[.]com`): replace `[.]` with `.`. Read it from the path in `VIGINUM_CSV` (the integrator puts the file in the worker image; locally `bash evals/download_data.sh` and point `VIGINUM_CSV` at `evals/data/viginum/portal_kombat_domains.csv`).
   - Fact checks: Google Fact Check Tools API (`GOOGLE_FACTCHECK_API_KEY`) per claim; each match is a context item with `fact_check` set and `text` = reviewed claim + verdict.
   - Then GDELT (1 request / 5 s: queue and cache), Gemini grounded search (`GEMINI_API_KEY`, D15), Oxylabs (D7).
   - Budget: one stage call times out after **120 s** (`STAGE_TIMEOUT_SECS`); fetch concurrently, cap per-site time, and report counts with `progress.report("14 sources so far")`. A failing adapter must not fail the stage: skip it and note it in the progress.
   - Done when: a pasted Italian or English news text on the VPS gets ≥ 3 context items with full bodies and a `sources[]` entry per outlet, inside 120 s.
2. **`story`** (`pipeline/story/__init__.py: run`, plain `def`: CPU-bound). Multilingual embeddings (e.g. `intfloat/multilingual-e5-small`, revision pinned, loaded at import), cosine similarity to the document, threshold plus date window: set `similarity`, `in_story`, `story_reason` on every context item. Tone and claim support ignore items with `in_story = false`.
3. **Memory check** after both land: worker RSS on the VPS (Hostinger Docker stats or `docker stats`). lingua with all languages preloaded, the e5 model, the AI-core models and Chromium all share the 6 GB limit.
4. **Frontend** (`web/`), as soon as retrieve's first version is merged: `bun run build` → `web/dist`; relative `/api/...` URLs; types from `contracts/ts/api.d.ts`; progress with `EventSource("/api/analyses/{id}/events")`; highlights with `Array.from(paragraph).slice(start, end)` (code points). Result page per `docs/plan.md` §9: score per dimension with evidence count, three reasons with links, coverage view, "Show how we calculated this". No "propaganda / not" label (D4).
5. `EVALUATED_LANGUAGES` in `pipeline/extract/language.py`: add a language code only when mosearc's labelled set has real items in it.

## Lyreplus — AI core on real data
1. As soon as `retrieve` is live: run real texts on the VPS and read `/api/stats` (p50/p95 per stage) and worker memory. If `signals_single` is too slow on 2 vCPU, cut paragraphs/peers or switch to a smaller model; the analysis budget is 300 s in total.
2. Check the signals against real `retrieve` output with ck-lithium: full bodies, `wire_service` outlets, `in_story`, fact-check items. Fix mismatches on your side or ask ck-lithium; contract questions go to the integrator.
3. Fit the combiner (`python -m pipeline.score.fit`) as soon as mosearc's runner produces the fit file; commit `weights.json` with its `cv` block. Until then confidences are priors: say so in the explanation's wording, never claim calibration.
4. Optional (D14): explanation in the user's language.

## mosearc — evaluation, spec, pitch
1. **`SPEC.md`** rewrite from `docs/plan.md` and `DECISIONS.md` (overdue since 12:00). Then the integrator removes the "superseded" note from `AGENTS.md`.
2. **Runner** (`evals/src/propaganda_eval/runner.py`, CLI command `run`): for each `labelled.jsonl` item, `POST /api/analyses?force=true` to a **local** API with the limits off (`deploy/README.md`, "Local"): `{"kind": "url", "value": url}` when the item has a URL (needed for coordinated items: outlet, tracking IDs and VIGINUM checks need a domain), else `{"kind": "text", "value": text}`. Poll `GET /api/analyses/{id}` until `done` or `failed`. Write to `evals/results/` (gitignored):
   - `predictions.jsonl` for the harness: `scores.<dimension>` = `confidence`, or `null` when `abstained`; a failed analysis is marked `failed`, not counted as an abstention;
   - `fit.jsonl` for Lyreplus: `{"analysis": <the full record>, "single": 0|1, "coordinated": 0|1}`.
3. **Harness**: report failures separately from abstentions; add `eval --json evals/metrics.json` (numbers only, no item text). That file is committed and served by `/api/metrics` for the metrics page (the integrator points the API at it).
4. **Labelled set**: ~100 single-actor items in ≥ 3 languages and ~50 coordinated, labels from third parties only (fact-checkers via ClaimReview, EUvsDisinfo, VIGINUM), plus the hard-negative sets. **Do not commit article bodies**: commit `url`, labels, set, source, language; keep fetched text in `evals/data/` or let the runner submit the URL. Only short claim texts quoted by a fact-checker may sit in `labelled.jsonl` (make `text` optional when `url` is set). Replace the synthetic seed items once real ones exist.
5. **Demo inputs**: 3–5 items in at least two languages that show both dimensions; run them on the VPS after the last deploy and keep their IDs for `events?replay=true`.
6. **Pitch** (`docs/pitch/`): demo script by 18:00; video, description and submission text before Sun 09:00.

## Integrator (Degra02)
- LLM settings in the VPS `.env` (`LLM_*`, model `gemini-3.1-flash-lite`) and the provider keys (`GOOGLE_FACTCHECK_API_KEY`, `GEMINI_API_KEY`, Oxylabs) before retrieve lands.
- Worker image: VIGINUM CSV at `VIGINUM_CSV`; decide on Chromium for the extract browser fallback (memory vs readable sites; without it the fallback switches itself off).
- `/api/metrics` served from the committed `evals/metrics.json`.
- Review and merge each round; keep `main` deployable; update this file after every round.

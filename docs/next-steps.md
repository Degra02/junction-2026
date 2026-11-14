# Next steps (Sat 16:30 round)

Living task list per person, kept by the integrator. Agents: read your section, `AGENTS.md` and `DECISIONS.md` first; do only what is listed for your owner; ask the integrator before touching a folder you do not own.

## State of `main` (Sat 16:30)
- Live at <https://the4thlover.tech> (API docs: `/api/docs`). Every merge to `main` deploys; the deploy goes red if a stage fails to import.
- Stages on `main`: `extract`, `understand`, `signals_single`, `signals_coordinated`, `score`, `explain`. **`retrieve` and `story` are written but not merged**: `ck-lithium/retrieve` (14 commits, no PR yet, 5 behind `main`). Until they land every analysis has no context, `score` abstains and coordinated signals stay empty. **Merging that branch is the critical path.**
- Merged this round: #8 explain discloses uncalibrated confidences and writes in the reader's language; #9 `SPEC.md` rewrite, eval runner, harness failures and `--json`; #11 + #13 real labelled set (260 items, 12 languages, incl. 25 EUvsDisinfo cases); #12 `Input.explanation_language` in the contract and the cache key.
- `/api/metrics` reads the committed `evals/metrics.json` (404 until mosearc commits it). `web/` is not built yet: `/` has no UI.
- Confidences are still priors (`pipeline/score/weights.json`, `n = 0`): the explanation says so until the fit lands.

## Deadlines
| When | What |
|---|---|
| ~~Sat 16:00~~ missed | Real pasted text through the full pipeline on the VPS, with context: now as soon as `retrieve` is merged |
| Sat 18:00 | MVP green: retrieve + story live, frontend v1, first real metrics, demo script final |
| Sun 03:00 | Feature freeze |
| Sun 09:00 | Submission: video, description, repo public under MIT |

## Rules for every agent
- Own branch `<person>/<topic>`, rebased on `main`; PR every ~2 h; `mise run check` passes before asking for a merge. **Work pushed after a PR is merged does not reach `main`: open a new PR.**
- A dependency is `uv add <pkg>` on your branch; say in the PR why, and its size if it is large (the worker image and the VPS have 2 vCPU / 8 GB, worker limit 6 GB).
- Contract changes (`contracts/`), `pyproject.toml` conflicts, `mise.toml`, CI, `deploy/`, `README.md`, `docs/plan.md`: ask the integrator.
- Test a stage alone with `pipeline.common.fixtures.example_analysis()`; iterate on a finished analysis with `POST /api/analyses/{id}/rerun?from=<stage>`.
- Never commit secrets, scraped article text or downloaded datasets (`evals/data/` is gitignored).

## ck-lithium — land retrieve and story, then the frontend
1. **PR `ck-lithium/retrieve` now**, as it is: rebase on `main` (it applies without conflicts as of 16:30), `mise run check`, open the PR. Say in it: the new `tld` dependency, the e5 model size, and that VIGINUM is downloaded at run time when `VIGINUM_CSV` is unset. Further adapters go in later PRs.
2. **On the VPS after the deploy**: a pasted Italian or English news text gets ≥ 3 context items with full bodies and a `sources[]` entry per outlet, inside the 120 s stage budget. Post the analysis ID in the PR thread.
3. **Memory check**: worker RSS on the VPS (Hostinger Docker stats or `docker stats`) with lingua, e5, the AI-core models and Chromium loaded together; limit 6 GB.
4. **Frontend** (`web/`): `bun run build` → `web/dist`; relative `/api/...` URLs; types from `contracts/ts/api.d.ts`; progress with `EventSource("/api/analyses/{id}/events")` (`?replay=true` for the demo); highlights with `Array.from(paragraph).slice(start, end)` (code points). Result page per `docs/plan.md` §9: score per dimension with evidence count, three reasons with links, coverage view, "Show how we calculated this". No "propaganda / not" label (D4).
   - Explanation language (D14): send `explanation_language` (e.g. `it`) with the input; default English; offer the content language (`language.code` of an earlier analysis of the same input). Invalid codes get a 422 `invalid_input`.
   - Metrics page from `GET /api/metrics` (404 = not published yet: show "metrics coming").
   - Show the abstention reason when a dimension abstains, and the failed-step message when a step fails.
5. `EVALUATED_LANGUAGES` in `pipeline/extract/language.py`: the labelled set has real items in en 57, de 48, fr 41, es 41, it 37, nl 17 (ru, pl, pt, ro, sv, cs: under 6 each). Add the first six once the metrics are published.

## Lyreplus — AI core on real data
1. As soon as `retrieve` is live: run real texts on the VPS and read `/api/stats` (p50/p95 per stage) and worker memory. If `signals_single` is too slow on 2 vCPU, cut paragraphs/peers or switch to a smaller model; the analysis budget is 300 s in total.
2. Check the signals against real `retrieve` output with ck-lithium: full bodies, `wire_service` outlets, `in_story`, fact-check items. Fix mismatches on your side or ask ck-lithium; contract questions go to the integrator.
3. **Fit the combiner** when the integrator hands over `evals/results/fit.jsonl` from the VPS run (after retrieve is deployed): `python -m pipeline.score.fit`, commit `weights.json` with its `cv` block. The priors note in the explanation disappears by itself once `n > 0`.
4. Re-run the demo items with `rerun?from=signals_single` after each signal or weight change and compare with mosearc.

## mosearc — evaluation, metrics, pitch
1. **Metrics**: after the integrator's VPS run, `mise run eval -- eval evals/results/predictions.jsonl --json evals/metrics.json` and commit `evals/metrics.json` (numbers only). The API image serves it at `/api/metrics` on the next deploy.
2. **Demo inputs** (`docs/pitch/demo-script.md`): once retrieve and story are live, submit each item on the VPS (`?force=true`), keep the clean runs and fill in the analysis IDs; swap in backups that score without evidence.
3. **Pitch** (`docs/pitch/`): demo script final by 18:00 (metrics beat once the numbers exist); video, description and submission text before Sun 09:00.

## Integrator (Degra02)
- Review and merge `ck-lithium/retrieve` as soon as the PR is up; watch the worker image build (e5 model) and the deploy.
- Then the eval run on the VPS host, limits off for the run and restored after: `PYTHONPATH=evals/src uv run --frozen python -m propaganda_eval.cli run --api http://127.0.0.1:8080 --concurrency 2`. `fit.jsonl` → Lyreplus, `predictions.jsonl` → mosearc.
- Confirm the VPS `.env`: `LLM_*` (`gemini-3.1-flash-lite`), `GOOGLE_FACTCHECK_API_KEY`, `GEMINI_API_KEY`, Oxylabs.
- Decide on Chromium for the extract browser fallback (memory vs readable sites) after ck-lithium's memory check.
- Keep `main` deployable; update this file after every round.

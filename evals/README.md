# evals/

Evaluation of the propaganda detection pipeline: the labelled set, the runner that puts it through the API, and the harness that turns the results into the metrics page (`/api/metrics`).

## Quick start

```bash
# From the repo root: the harness is part of the root uv project (dev dependencies).
mise run eval -- validate                              # check labelled.jsonl
mise run eval -- stats                                 # counts per set, dimension, language

# Local API with the limits off (deploy/README.md, "Local"), in another terminal:
RATE_LIMIT_PER_MINUTE=0 MAX_ANALYSES_PER_HOUR=0 MAX_CONCURRENT_ANALYSES=8 \
  MAX_CONCURRENT_INFERENCE=4 mise run dev

mise run eval -- run                                   # every item → evals/results/
mise run eval -- eval evals/results/predictions.jsonl --json evals/metrics.json
uv run python -m pipeline.score.fit evals/results/fit.jsonl --dry-run   # combiner fit (Lyreplus)
```

Tests live in `evals/tests/` and run with `mise run check`.

## labelled.jsonl

Ground truth. Labels come from third parties (fact-checkers via ClaimReview, EUvsDisinfo, VIGINUM, the publisher's own identity), never from our reading of the text. One JSON object per line:

```jsonc
{
  "id":         "fcd_it_001",
  "url":        "https://…",              // the content to analyse; the pipeline fetches it
  "text":       "…",                      // only a short claim quoted verbatim by a fact-checker
  "language":   "it",                     // ISO 639-1
  "labels": {
    "single":      true,                  // true | false | null
    "coordinated": null
  },
  "set":        "fact_checker_debunk",
  "source":     "ClaimReview feed (Pagella Politica)",
  "source_url": "https://…",              // the page that establishes the label
  "notes":      "rating: Falso"
}
```

- Every item has a `url` or a `text`. **Never commit article bodies** (copyright, research-only data): `validate` rejects a `text` over 600 characters. The runner submits the URL when there is one (coordinated signals need the outlet domain, tracking IDs and the VIGINUM check), else the text.
- `null` = no third-party label for that dimension; the item is left out of that dimension's metrics. A fact-checker's debunk says nothing about coordination; VIGINUM lists a domain as part of a network, which says nothing about the techniques in one article.

### Sets (plan §8)

| Set | Labels | Source of the label |
|-----|--------|---------------------|
| `fact_checker_debunk` | single=true | ClaimReview rating false/misleading |
| `euvsDisinfo` | single=true | EUvsDisinfo database case |
| `viginum_pravda` | coordinated=true | Domain on VIGINUM's Portal Kombat list |
| `mainstream` | both false | Straight reporting by an established outlet |
| `hard_fact_checks` | both false | Fact-check articles quoting the claim |
| `hard_satire` | both false | Satire outlets |
| `hard_op_eds` | both false | Opinion sections |
| `hard_emotional` | both false | Emotional but accurate reporting |
| `hard_wire_copy` | both false | Agency copy (AP, Reuters, AFP, dpa, EFE, ANSA) republished by many outlets |
| `hard_press_releases` | both false | Government/corporate releases and their republications |

Positives cover pro-Kremlin operations (EUvsDisinfo, VIGINUM) plus domestic misinformation (fact-checkers). The `known_networks` family reads the same VIGINUM list that labels `viginum_pravda`: read the coordinated metrics next to the ablation row "without known_networks".

## Runner (`run`)

Submits each item to `POST /api/analyses?force=true`, polls `GET /api/analyses/{id}` until `done` or `failed`, and appends one line per item to `evals/results/` (gitignored):

- `predictions.jsonl` (input of `eval`):
  ```jsonc
  {"item_id": "fcd_it_001", "analysis_id": "…", "pipeline_version": "dev", "failed": false,
   "scores": {"single": 0.82, "coordinated": null},          // null = abstained
   "abstain_reasons": {"single": null, "coordinated": "Only 2 other items…"},
   "skipped_steps": ["story"],
   "ablation": {"single": {"techniques": 0.61, "fact_checks": 0.4}, "coordinated": {}}}
  ```
  `failed: true` when the analysis failed, finished with a failed step, or timed out: the pipeline broke, it did not abstain. `ablation` is each dimension's confidence with one family's evidence removed, scored by `pipeline.score` with the current weights.
- `fit.jsonl` (input of `python -m pipeline.score.fit`): `{"item_id", "analysis": <record>, "single": 0|1|null, "coordinated": 0|1|null}`, finished analyses only.

Re-running resumes: items already finished are skipped, failed ones run again. `--fresh` starts over, `--only ID…` runs a subset, `--api` points elsewhere (never the VPS for a full run: it has rate and spend limits). To measure a change in signals, the combiner or the explanation on the same retrieved context, re-run the stored analyses (`POST /api/analyses/{id}/rerun?from=<stage>`) instead.

## Harness (`eval`)

Per dimension: precision, recall, F1, FPR with Wilson 95% intervals; FPR per hard-negative set; metrics per set and per language; calibration table; abstain rate (of finished analyses) and failure rate, reported apart; missing items (no prediction); ablation per family.

`--output report.md` writes the markdown report, `--json evals/metrics.json` the numbers only (no item text or URLs). `evals/metrics.json` is committed and served unchanged by `/api/metrics` for the metrics page.

## Fixtures

`fixtures/analysis_positive.json` and `fixtures/analysis_negative.json` are finished `Analysis` records whose evidence the combiner maps. Use them to test a stage alone.

## External data

```bash
bash evals/download_data.sh
```

Downloads into `evals/data/` (gitignored): SemEval-2020 Task 11 PTC v2 (technique eval, research-only) and the VIGINUM Portal Kombat domain CSV (domains defanged: `pravda-de[.]com`).

## File layout

```
evals/
├── labelled.jsonl                  # ground truth (committed: URLs, labels, short quoted claims)
├── metrics.json                    # latest metrics, numbers only (committed, /api/metrics)
├── download_data.sh                # external datasets → data/
├── fixtures/                       # Analysis records for stage tests
├── tests/                          # run by `mise run check`
├── src/propaganda_eval/
│   ├── labelled.py                 # item format, load, validate, stats
│   ├── runner.py                   # labelled items → local API → predictions.jsonl, fit.jsonl
│   ├── metrics.py                  # binary metrics, Wilson CI, calibration, ablation, JSON
│   ├── format.py                   # markdown tables
│   └── cli.py                      # validate | stats | run | eval
├── data/                           # gitignored: external datasets
└── results/                        # gitignored: runner output, reports
```

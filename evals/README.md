# evals/

Evaluation harness for the propaganda detection pipeline.

## Quick start

```bash
# From the repo root: the harness is part of the root uv project (dev dependencies).
mise run eval -- validate                 # check labelled.jsonl format
mise run eval -- stats                    # labelled set statistics
mise run eval -- eval preds.jsonl         # evaluate predictions
```

Tests live in `evals/tests/` and run with `mise run check` (every fixture must be a valid `Analysis` whose signals the combiner maps).

## labelled.jsonl

Ground-truth set for the eval harness and, once a runner turns each item into a finished `Analysis`, for the combiner fit (`python -m pipeline.score.fit`, which reads `{"analysis": <Analysis>, "single": 1|0|null, "coordinated": 1|0|null}` per line). One JSON object per line:

```jsonc
{
  "id":         "sa_pos_042",
  "text":       "article text…",
  "url":        "https://…",             // optional
  "language":   "en",                     // ISO 639-1
  "labels": {
    "single":      true,                  // matches pipeline Scores.single
    "coordinated": false                  // matches pipeline Scores.coordinated
  },
  "set":        "fact_checker_debunk",    // evaluation set name
  "source":     "Google Fact Check API",  // provenance
  "source_url": "https://…",
  "notes":      ""
}
```

### Sets (plan §8)

| Set | Dimension | Description |
|-----|-----------|-------------|
| `fact_checker_debunk` | single=true | Claims debunked by fact-checkers |
| `euvsDisinfo` | single=true | EUvsDisinfo database cases |
| `viginum_pravda` | coordinated=true | VIGINUM Portal Kombat domains |
| `mainstream` | both=false | Mainstream reporting on same events |
| `hard_fact_checks` | both=false | Fact-checks quoting the claim |
| `hard_satire` | both=false | Satirical articles |
| `hard_op_eds` | both=false | Legitimate opinion journalism |
| `hard_emotional` | both=false | Emotional but accurate reporting |
| `hard_wire_copy` | both=false | Wire services (AP, Reuters, ANSA) |
| `hard_press_releases` | both=false | Corporate/government press releases |

Target: ~100 single-actor + ~50 coordinated positives, across 3+ languages. The seed `labelled.jsonl` has 10 synthetic examples showing the format.

## Predictions format

One JSON object per line matching a labelled item by `item_id`:

```jsonc
{"item_id": "sa_pos_042", "scores": {"single": 0.82, "coordinated": null}}
// null = pipeline abstained on that dimension
```

## Metrics

Per dimension: precision, recall, F1, FPR, calibration table, abstain rate, Wilson 95% CI.
Per hard-negative set: FPR (the main quality signal — propaganda detectors must not flag fact-checks or satire).

## Fixtures

`fixtures/analysis_positive.json` and `fixtures/analysis_negative.json` are minimal Analysis records matching the pipeline contract (`contracts/fixtures/analysis.json`). Use them for stage testing.

## External data

```bash
bash download_data.sh
```

Downloads into `data/` (gitignored):
- SemEval-2020 Task 11 PTC v2 from Zenodo (technique eval)
- VIGINUM Portal Kombat domain CSV from GitHub (domains are defanged: `pravda-de[.]com`)

## File layout

```
evals/
├── labelled.jsonl                     # seed ground-truth (committed)
├── download_data.sh                   # external dataset download
├── tests/                             # run by `mise run check`
├── README.md                          # this file
├── fixtures/
│   ├── analysis_positive.json         # positive fixture for stage testing
│   └── analysis_negative.json         # negative fixture for stage testing
├── src/propaganda_eval/
│   ├── labelled.py                    # LabelledItem format, load/save/validate
│   ├── metrics.py                     # binary metrics, Wilson CI, calibration
│   ├── format.py                      # GitHub-markdown table output
│   └── cli.py                         # CLI entry point
├── data/                              # gitignored: external datasets
└── results/                           # gitignored: prediction files
```

# Evaluation harness

Propaganda technique detection eval for the Hostinger "Decode the Noise" challenge. Measures per-technique precision, recall and F1; reports false-positive rate on hard-negative sets (fact-checks, satire, op-eds, wire copy). Feeds the metrics table in the submission README and the Nemotron/Oxylabs sponsor criteria.

## Quickstart

```bash
cd evals
bash download_data.sh          # SemEval-2020 PTC v2, 1.1 MB from Zenodo
uv sync                        # install Python deps
uv run propaganda-eval info    # verify: 371 train, 75 dev, 14 techniques
```

The dataset is gitignored (research-only licence — **never commit**). Each machine downloads its own copy.

## Dataset

| Name | Articles | Spans | Techniques | Access |
|---|---|---|---|---|
| SemEval-2020 Task 11 / PTC v2 | 371 train + 75 dev | 6 129 | 14 (18 original, merged) | [Zenodo 3952415](https://zenodo.org/records/3952415), open |
| SemEval-2023 Task 3 | multilingual | paragraph-level | 23 in 6 categories | Registration, manual approval |
| SemEval-2024 Task 4 | memes | multimodal | 22 | Registration + passcode |

Only the 2020 data is usable now. The eval split is a deterministic 85/15 holdout of the 371 train articles (seed 42), because the official dev set has no technique gold labels.

## Commands

| Command | What it does |
|---|---|
| `uv run propaganda-eval info` | Dataset stats and technique distribution |
| `uv run propaganda-eval baselines` | Generate oracle + random prediction files |
| `uv run propaganda-eval eval <pred>.jsonl` | Per-technique and per-category P / R / F1 |
| `uv run propaganda-eval compare <a>.jsonl <b>.jsonl …` | Side-by-side model comparison table |
| `uv run propaganda-eval hard-negatives <pred>.jsonl --set-name <set>` | FPR on one hard-negative set |

Add `--output report.md` to `eval` or `compare` to write the table to a file.

## Running a model against the eval set

Set `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` in the root `.env` (same client as the main app), then:

```bash
uv run python -m propaganda_eval.run_model \
    --model-name "nemotron-zero-shot" \
    --output results/nemotron_zero_shot.jsonl \
    --max-articles 5   # remove for the full 56-article eval split
```

The script sends each article to the model, parses the JSON response, validates spans against the source text, and writes one JSONL line per detected span.

## Prediction format (contract for AI core)

One JSONL line per detected span. Fields:

| Field | Type | Required | Notes |
|---|---|---|---|
| `article_id` | string | yes | Numeric ID from the dataset filename, e.g. `"111111111"` |
| `technique` | string | yes | Canonical name from `taxonomy.py` (see table below) |
| `start` | int | yes | Character offset, 0-indexed, inclusive |
| `end` | int | yes | Character offset, 0-indexed, exclusive |
| `confidence` | float | no | 0–1, defaults to 1.0 |

Example:
```json
{"article_id": "111111111", "technique": "Loaded_Language", "start": 123, "end": 145, "confidence": 0.95}
```

## Techniques (14 labels)

| Canonical name | Display name | Category |
|---|---|---|
| `Appeal_to_Authority` | Appeal to Authority | Justification |
| `Appeal_to_fear-prejudice` | Appeal to Fear/Prejudice | Justification |
| `Bandwagon,Reductio_ad_hitlerum` | Bandwagon / Reductio ad Hitlerum | Justification |
| `Flag-Waving` | Flag-Waving | Justification |
| `Causal_Oversimplification` | Causal Oversimplification | Simplification |
| `Black-and-White_Fallacy` | Black-and-White Fallacy | Simplification |
| `Whataboutism,Straw_Men,Red_Herring` | Whataboutism / Straw Man / Red Herring | Distraction |
| `Slogans` | Slogans | Call |
| `Thought-terminating_Cliches` | Thought-terminating Cliches | Call |
| `Loaded_Language` | Loaded Language | Manipulation |
| `Exaggeration,Minimisation` | Exaggeration / Minimisation | Manipulation |
| `Repetition` | Repetition | Manipulation |
| `Name_Calling,Labeling` | Name Calling / Labeling | Attack on Reputation |
| `Doubt` | Doubt | Attack on Reputation |

The 6 categories are aligned with SemEval-2023 Task 3. Metrics are reported at both levels.

## Hard-negative sets

These are texts that must NOT be flagged. Each set has its own FPR in the report.

| Set | Purpose | Source |
|---|---|---|
| `fact_checks` | Articles that quote propaganda to debunk it | Collected by team |
| `satire` | Satirical articles using exaggeration for humour | Collected by team |
| `op_eds` | Legitimate opinion journalism with strong language | Collected by team |
| `wire_copy` | AP, Reuters, ANSA syndicated content appearing on many sites | Collected by team |
| `press_releases` | Corporate / government press releases | Collected by team |

Add items as `.txt` + `.meta.json` pairs in `data/hard_negatives/<set_name>/`. The `.meta.json` records the source:

```json
{
  "source_url": "https://example.com/article",
  "source_name": "Reuters",
  "set_name": "wire_copy",
  "notes": "AP wire story syndicated to 40+ outlets"
}
```

## What feeds the submission

| Submission section | Source |
|---|---|
| Metrics table in README | `propaganda-eval compare` across all models |
| Nemotron criterion ("how you improved outputs") | Same table: zero-shot → verifier gains |
| Oxylabs criterion ("honest about failures") | Hard-negative FPR per set |
| Demo screen | Live eval results shown alongside the verdict |
| Confidence score explanation | Per-technique metrics justify the signal weights |

## File layout

```
evals/
├── download_data.sh                   # dataset download for each machine
├── pyproject.toml                     # Python deps (uv sync)
├── README.md                          # this file
├── src/propaganda_eval/
│   ├── taxonomy.py                    # 14 techniques → 6 categories
│   ├── dataset.py                     # SemEval-2020 loader + train/eval split
│   ├── metrics.py                     # P/R/F1, span IoU matching, hard-neg FPR
│   ├── format.py                      # GitHub-markdown table output
│   ├── cli.py                         # CLI entry point
│   ├── baselines.py                   # oracle + random prediction generators
│   ├── hard_negatives.py              # hard-negative set management
│   └── run_model.py                   # run any LLM via LLM_BASE_URL/KEY/MODEL
├── data/                              # gitignored: datasets + hard negatives
│   ├── datasets/                      # SemEval-2020 PTC v2 (from download_data.sh)
│   └── hard_negatives/{set_name}/     # .txt + .meta.json pairs
└── results/                           # gitignored: prediction JSONL files
```

# Evaluation harness

Propaganda technique detection eval for the Hostinger "Decode the Noise" challenge.

## Setup

```bash
cd evals
uv sync
```

## Dataset

SemEval-2020 Task 11 PTC v2 (1.1 MB, 371 train articles, 14 techniques).
Download once — **never commit** (research-only licence):

```bash
mkdir -p data && cd data
curl -L -o datasets-v2.tgz "https://zenodo.org/records/3952415/files/datasets-v2.tgz?download=1"
tar xzf datasets-v2.tgz
```

## Commands

```bash
# Dataset stats
uv run propaganda-eval info

# Generate oracle + random baselines
uv run propaganda-eval baselines

# Evaluate one model's predictions
uv run propaganda-eval eval results/<model>.jsonl --model-name "Model name"

# Compare models side by side
uv run propaganda-eval compare results/oracle.jsonl results/random.jsonl

# Hard-negative FPR
uv run propaganda-eval hard-negatives results/hn_<set>.jsonl --set-name fact_checks
```

## Running a model

Set `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` in `.env`, then:

```bash
uv run python -m propaganda_eval.run_model \
    --model-name "nemotron-zero-shot" \
    --output results/nemotron_zero_shot.jsonl \
    --max-articles 5  # remove for full run
```

## Prediction format

JSONL, one line per detected span:

```json
{"article_id": "111111111", "technique": "Loaded_Language", "start": 123, "end": 145, "confidence": 0.95}
```

Techniques must use canonical names from `taxonomy.py`.

## Hard negatives

Place `.txt` + `.meta.json` pairs in `data/hard_negatives/<set_name>/`:
- `fact_checks/` — articles quoting propaganda to debunk it
- `satire/` — satirical articles
- `op_eds/` — legitimate opinion journalism
- `wire_copy/` — AP, Reuters syndicated content
- `press_releases/` — corporate/government press releases

## What goes in the final report

| Metric | Where |
|---|---|
| Per-technique P / R / F1 | `propaganda-eval eval` |
| Per-category P / R / F1 | same |
| Model comparison table | `propaganda-eval compare` |
| Hard-negative FPR per set | `propaganda-eval hard-negatives` |
| Gemma fine-tuned vs zero-shot vs Nemotron | compare all three JSONL files |

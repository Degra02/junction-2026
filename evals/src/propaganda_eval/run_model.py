"""Run a model against the eval set and produce predictions JSONL.

Usage:
    uv run python -m propaganda_eval.run_model \
        --model-name "nemotron-zero-shot" \
        --output results/nemotron_zero_shot.jsonl

The model is called via the OpenAI-compatible client configured by
LLM_BASE_URL / LLM_API_KEY / LLM_MODEL (same as the main app).

Prediction contract — the model receives an article and must return JSON:
[
  {
    "technique": "Loaded_Language",
    "start": 123,
    "end": 145,
    "explanation": "why this span is manipulative"
  },
  ...
]

Techniques must use the canonical names from taxonomy.SEMEVAL2020_TECHNIQUES.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from .dataset import Article, load_semeval2020, train_dev_split
from .taxonomy import SEMEVAL2020_TECHNIQUES, TECHNIQUE_TO_CATEGORY, technique_display

SYSTEM_PROMPT = """You are a propaganda technique detector. Given a news article, identify spans that use propaganda techniques and classify each span.

For each propaganda span found, return a JSON array of objects with:
- "technique": one of the canonical technique names listed below
- "start": character offset where the span starts (0-indexed, inclusive)
- "end": character offset where the span ends (0-indexed, exclusive)
- "explanation": one sentence explaining why this span is manipulative

Canonical technique names:
{techniques}

Rules:
- Only flag spans that genuinely use a propaganda technique.
- Every span must be an exact substring of the article at the given offsets.
- If no propaganda is found, return an empty array: []
- Return ONLY the JSON array, no other text.
"""

USER_PROMPT = """Analyse this article for propaganda techniques. Return a JSON array of detected spans.

Article text:
---
{text}
---"""


def build_system_prompt() -> str:
    techniques_list = "\n".join(
        f"- {t} ({technique_display(t)}): category {TECHNIQUE_TO_CATEGORY[t]}"
        for t in SEMEVAL2020_TECHNIQUES
    )
    return SYSTEM_PROMPT.format(techniques=techniques_list)


def call_model(text: str, client, model: str) -> list[dict]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": USER_PROMPT.format(text=text)},
        ],
        temperature=0.0,
        max_tokens=4096,
    )

    content = response.choices[0].message.content.strip()
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if not match:
        return []

    try:
        spans = json.loads(match.group())
    except json.JSONDecodeError:
        return []

    valid = []
    for s in spans:
        if not isinstance(s, dict):
            continue
        tech = s.get("technique", "")
        start = s.get("start")
        end = s.get("end")
        if tech not in SEMEVAL2020_TECHNIQUES:
            continue
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start < 0 or end <= start or end > len(text):
            continue
        actual = text[start:end]
        if len(actual.strip()) < 3:
            continue
        valid.append(s)

    return valid


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a model against the eval set")
    parser.add_argument("--model-name", required=True, help="Name for the results file")
    parser.add_argument("--output", required=True, help="Output predictions JSONL path")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--max-articles", type=int, default=None, help="Limit articles for testing")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API calls")
    args = parser.parse_args()

    base_url = os.environ.get("LLM_BASE_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")

    if not all([base_url, api_key, model]):
        print("Set LLM_BASE_URL, LLM_API_KEY, LLM_MODEL in .env", file=sys.stderr)
        sys.exit(1)

    from openai import OpenAI
    client = OpenAI(base_url=base_url, api_key=api_key)

    data_dir = args.data_dir or str(Path(__file__).resolve().parents[2] / "data")
    train, _ = load_semeval2020(data_dir)
    _, eval_articles = train_dev_split(train)

    articles = list(eval_articles.values())
    if args.max_articles:
        articles = articles[:args.max_articles]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Running {args.model_name} on {len(articles)} articles...")
    total_preds = 0
    errors = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for i, article in enumerate(articles):
            try:
                spans = call_model(article.text, client, model)
                for s in spans:
                    json.dump({
                        "article_id": article.article_id,
                        "technique": s["technique"],
                        "start": s["start"],
                        "end": s["end"],
                        "confidence": 1.0,
                    }, f)
                    f.write("\n")
                    total_preds += 1
                status = f"[{i+1}/{len(articles)}] {article.article_id}: {len(spans)} spans"
            except Exception as e:
                errors += 1
                status = f"[{i+1}/{len(articles)}] {article.article_id}: ERROR {e}"

            print(status)
            if args.delay > 0 and i < len(articles) - 1:
                time.sleep(args.delay)

    print(f"\nDone. {total_preds} predictions written to {output_path}")
    if errors:
        print(f"  {errors} articles had errors")


if __name__ == "__main__":
    main()

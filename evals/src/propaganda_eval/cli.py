"""CLI entry point for the propaganda eval harness."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .dataset import load_semeval2020, train_dev_split
from .format import format_full_report
from .metrics import (
    EvalResult,
    Prediction,
    evaluate_hard_negatives,
    evaluate_technique_classification,
    evaluate_span_identification,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Propaganda technique eval harness")
    sub = parser.add_subparsers(dest="command")

    info_p = sub.add_parser("info", help="Show dataset stats")
    info_p.add_argument("--data-dir", default=_default_data_dir())

    eval_p = sub.add_parser("eval", help="Evaluate predictions against gold labels")
    eval_p.add_argument("predictions", help="Path to predictions JSONL file")
    eval_p.add_argument("--data-dir", default=_default_data_dir())
    eval_p.add_argument("--model-name", default="")
    eval_p.add_argument("--iou-threshold", type=float, default=0.5)
    eval_p.add_argument("--output", help="Write report to file")

    compare_p = sub.add_parser("compare", help="Compare multiple prediction files")
    compare_p.add_argument("predictions", nargs="+", help="Prediction JSONL files")
    compare_p.add_argument("--data-dir", default=_default_data_dir())
    compare_p.add_argument("--output", help="Write report to file")

    hn_p = sub.add_parser("hard-negatives", help="Evaluate hard-negative FPR")
    hn_p.add_argument("predictions", help="Predictions JSONL on hard-negative texts")
    hn_p.add_argument("--set-name", required=True)

    base_p = sub.add_parser("baselines", help="Generate oracle and random baselines")
    base_p.add_argument("--data-dir", default=_default_data_dir())
    base_p.add_argument("--output-dir", default=str(Path(_default_data_dir()).parent / "results"))

    args = parser.parse_args()

    if args.command == "info":
        _cmd_info(args)
    elif args.command == "eval":
        _cmd_eval(args)
    elif args.command == "compare":
        _cmd_compare(args)
    elif args.command == "hard-negatives":
        _cmd_hard_negatives(args)
    elif args.command == "baselines":
        _cmd_baselines(args)
    else:
        parser.print_help()


def _default_data_dir() -> str:
    return os.environ.get(
        "EVAL_DATA_DIR",
        str(Path(__file__).resolve().parents[2] / "data"),
    )


def _cmd_info(args: argparse.Namespace) -> None:
    train, dev = load_semeval2020(args.data_dir)
    train_split, eval_split = train_dev_split(train)

    total_spans = sum(len(a.spans) for a in train.values())
    print(f"SemEval-2020 Task 11 PTC v2")
    print(f"  Train articles:     {len(train)}")
    print(f"  Dev articles:       {len(dev)} (no TC gold labels)")
    print(f"  Total spans:        {total_spans}")
    print(f"  Train/eval split:   {len(train_split)} / {len(eval_split)}")
    print()

    from collections import Counter
    tech_counts = Counter(s.technique for a in train.values() for s in a.spans)
    print("Technique distribution:")
    for tech, count in tech_counts.most_common():
        print(f"  {tech:45s} {count:5d}")


def _cmd_eval(args: argparse.Namespace) -> None:
    train, _ = load_semeval2020(args.data_dir)
    _, eval_articles = train_dev_split(train)

    gold_spans = [s for a in eval_articles.values() for s in a.spans]
    pred_spans = _load_predictions(args.predictions)

    result = evaluate_technique_classification(
        gold_spans, pred_spans, iou_threshold=args.iou_threshold
    )
    result.model_name = args.model_name or Path(args.predictions).stem
    result.total_articles = len(eval_articles)

    report = format_full_report([result])
    print(report)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nReport written to {args.output}")


def _cmd_compare(args: argparse.Namespace) -> None:
    train, _ = load_semeval2020(args.data_dir)
    _, eval_articles = train_dev_split(train)

    gold_spans = [s for a in eval_articles.values() for s in a.spans]

    results = []
    for pred_path in args.predictions:
        preds = _load_predictions(pred_path)
        r = evaluate_technique_classification(gold_spans, preds)
        r.model_name = Path(pred_path).stem
        r.total_articles = len(eval_articles)
        results.append(r)

    report = format_full_report(results)
    print(report)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")


def _cmd_hard_negatives(args: argparse.Namespace) -> None:
    preds_data = _load_hard_negative_predictions(args.predictions)
    result = evaluate_hard_negatives(
        args.set_name,
        preds_data["texts"],
        preds_data["predictions"],
    )
    print(f"Hard-negative set: {result.set_name}")
    print(f"  Items:            {result.total_items}")
    print(f"  False positives:  {result.false_positives}")
    print(f"  FPR:              {result.fpr:.3f}")
    if result.false_positive_details:
        print("\nFalse positive details:")
        for d in result.false_positive_details:
            print(f"  [{d['item_index']}] {d['predicted_techniques']}")
            print(f"      {d['text_preview'][:100]}...")


def _cmd_baselines(args: argparse.Namespace) -> None:
    from .baselines import generate_baselines
    generate_baselines(args.data_dir, args.output_dir)


def _load_predictions(path: str) -> list[Prediction]:
    preds = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            preds.append(Prediction(
                article_id=d["article_id"],
                technique=d["technique"],
                start=d["start"],
                end=d["end"],
                confidence=d.get("confidence", 1.0),
            ))
    return preds


def _load_hard_negative_predictions(path: str) -> dict:
    texts = []
    predictions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            texts.append(d["text"])
            preds = [
                Prediction(
                    article_id="",
                    technique=p["technique"],
                    start=p["start"],
                    end=p["end"],
                    confidence=p.get("confidence", 1.0),
                )
                for p in d.get("predictions", [])
            ]
            predictions.append(preds)
    return {"texts": texts, "predictions": predictions}


if __name__ == "__main__":
    main()

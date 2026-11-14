"""CLI entry point for the propaganda eval harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .format import format_full_report
from .labelled import load_labelled, stats
from .metrics import Prediction, evaluate


def main() -> None:
    parser = argparse.ArgumentParser(description="Propaganda detection eval harness")
    sub = parser.add_subparsers(dest="command")

    stats_p = sub.add_parser("stats", help="Labelled set statistics")
    stats_p.add_argument("--labelled", default=_default_labelled(), help="Path to labelled.jsonl")

    eval_p = sub.add_parser("eval", help="Evaluate pipeline predictions against labels")
    eval_p.add_argument("predictions", help="Path to predictions JSONL")
    eval_p.add_argument("--labelled", default=_default_labelled(), help="Path to labelled.jsonl")
    eval_p.add_argument("--threshold", type=float, default=0.5)
    eval_p.add_argument("--output", help="Write report to file")

    validate_p = sub.add_parser("validate", help="Validate labelled.jsonl format")
    validate_p.add_argument("--labelled", default=_default_labelled())

    args = parser.parse_args()

    if args.command == "stats":
        _cmd_stats(args)
    elif args.command == "eval":
        _cmd_eval(args)
    elif args.command == "validate":
        _cmd_validate(args)
    else:
        parser.print_help()


def _default_labelled() -> str:
    return str(Path(__file__).resolve().parents[2] / "labelled.jsonl")


def _cmd_stats(args: argparse.Namespace) -> None:
    items = load_labelled(Path(args.labelled))
    s = stats(items)
    print(f"Labelled set: {s['total']} items")
    print("\nBy set:")
    for name, count in s["by_set"].items():
        print(f"  {name:30s} {count:5d}")
    print("\nBy dimension:")
    for dim, counts in s["by_dimension"].items():
        print(f"  {dim:20s}  pos={counts['pos']:4d}  neg={counts['neg']:4d}")
    print("\nBy language:")
    for lang, count in s["by_language"].items():
        print(f"  {lang:5s} {count:5d}")


def _cmd_eval(args: argparse.Namespace) -> None:
    items = load_labelled(Path(args.labelled))
    predictions = _load_predictions(args.predictions)
    result = evaluate(items, predictions, threshold=args.threshold)
    report = format_full_report(result)
    print(report)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nReport written to {args.output}")


def _cmd_validate(args: argparse.Namespace) -> None:
    try:
        items = load_labelled(Path(args.labelled))
        s = stats(items)
        print(f"OK: {s['total']} items, {len(s['by_set'])} sets, {len(s['by_language'])} languages")
    except Exception as e:
        print(f"INVALID: {e}", file=sys.stderr)
        sys.exit(1)


def _load_predictions(path: str) -> dict[str, Prediction]:
    """Load predictions JSONL: one line per item.

    Format:
    {"item_id": "sa_pos_042", "scores": {"single": 0.82, "coordinated": null}}

    null means the pipeline abstained on that dimension.
    """
    preds: dict[str, Prediction] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            preds[d["item_id"]] = Prediction(
                item_id=d["item_id"],
                scores=d["scores"],
            )
    return preds


if __name__ == "__main__":
    main()

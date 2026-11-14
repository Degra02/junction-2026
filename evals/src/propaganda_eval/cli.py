"""CLI entry point for the propaganda eval harness (`mise run eval -- <command>`)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .format import format_full_report
from .labelled import load_labelled, stats
from .metrics import Prediction, evaluate, to_json

EVALS = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Propaganda detection eval harness")
    sub = parser.add_subparsers(dest="command")
    labelled = str(EVALS / "labelled.jsonl")

    stats_p = sub.add_parser("stats", help="Labelled set statistics")
    stats_p.add_argument("--labelled", default=labelled, help="Path to labelled.jsonl")

    validate_p = sub.add_parser("validate", help="Validate labelled.jsonl format")
    validate_p.add_argument("--labelled", default=labelled)

    run_p = sub.add_parser("run", help="Run the labelled items through a local API")
    run_p.add_argument("--labelled", default=labelled)
    run_p.add_argument("--api", default="http://127.0.0.1:8080", help="API base URL")
    run_p.add_argument("--out", default=str(EVALS / "results"), help="Output directory")
    run_p.add_argument("--concurrency", type=int, default=4)
    run_p.add_argument("--timeout", type=float, default=420.0, help="Seconds per analysis")
    run_p.add_argument("--only", nargs="+", metavar="ID", help="Run only these item IDs")
    run_p.add_argument("--fresh", action="store_true", help="Discard earlier results")

    eval_p = sub.add_parser("eval", help="Evaluate pipeline predictions against labels")
    eval_p.add_argument("predictions", help="Path to predictions JSONL")
    eval_p.add_argument("--labelled", default=labelled, help="Path to labelled.jsonl")
    eval_p.add_argument("--threshold", type=float, default=0.5)
    eval_p.add_argument("--output", help="Write the markdown report to this file")
    eval_p.add_argument(
        "--json",
        dest="json_path",
        help="Write the metrics (numbers only) to this file, e.g. evals/metrics.json",
    )

    args = parser.parse_args()

    if args.command == "stats":
        _cmd_stats(args)
    elif args.command == "validate":
        _cmd_validate(args)
    elif args.command == "run":
        _cmd_run(args)
    elif args.command == "eval":
        _cmd_eval(args)
    else:
        parser.print_help()


def _cmd_stats(args: argparse.Namespace) -> None:
    items = load_labelled(Path(args.labelled))
    s = stats(items)
    print(f"Labelled set: {s['total']} items")
    print("\nBy set:")
    for name, count in s["by_set"].items():
        print(f"  {name:30s} {count:5d}")
    print("\nBy dimension:")
    for dim, c in s["by_dimension"].items():
        print(f"  {dim:20s}  pos={c['pos']:4d}  neg={c['neg']:4d}  unlabelled={c['unlabelled']:4d}")
    print("\nBy language:")
    for lang, count in s["by_language"].items():
        print(f"  {lang:5s} {count:5d}")


def _cmd_validate(args: argparse.Namespace) -> None:
    try:
        items = load_labelled(Path(args.labelled))
        s = stats(items)
        print(f"OK: {s['total']} items, {len(s['by_set'])} sets, {len(s['by_language'])} languages")
    except Exception as e:
        print(f"INVALID: {e}", file=sys.stderr)
        sys.exit(1)


def _cmd_run(args: argparse.Namespace) -> None:
    # Imported here: the runner loads the pipeline's contracts and combiner.
    from .runner import run

    items = load_labelled(Path(args.labelled))
    if args.only:
        unknown = set(args.only) - {i.id for i in items}
        if unknown:
            sys.exit(f"unknown item IDs: {', '.join(sorted(unknown))}")
        items = [i for i in items if i.id in set(args.only)]
    counts = asyncio.run(
        run(items, args.api, Path(args.out), args.concurrency, args.timeout, args.fresh)
    )
    print(f"\n{counts['done']} done, {counts['failed']} failed; results in {args.out}")


def _cmd_eval(args: argparse.Namespace) -> None:
    items = load_labelled(Path(args.labelled))
    predictions = _load_predictions(args.predictions)
    result = evaluate(items, predictions, threshold=args.threshold)
    report = format_full_report(result)
    print(report)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nReport written to {args.output}")
    if args.json_path:
        path = Path(args.json_path)
        path.write_text(json.dumps(to_json(result), indent=2) + "\n", encoding="utf-8")
        print(f"Metrics written to {path}")


def _load_predictions(path: str) -> dict[str, Prediction]:
    """Load predictions JSONL (written by `run`), one line per item:

    {"item_id": "fcd_it_001", "failed": false, "scores": {"single": 0.82, "coordinated": null},
     "ablation": {"single": {"techniques": 0.6}}, "pipeline_version": "sha-…"}

    A null score means the pipeline abstained on that dimension; `failed` means it broke.
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
                scores=d.get("scores") or {},
                failed=bool(d.get("failed", False)),
                ablation=d.get("ablation") or {},
                pipeline_version=d.get("pipeline_version") or "",
            )
    return preds


if __name__ == "__main__":
    main()

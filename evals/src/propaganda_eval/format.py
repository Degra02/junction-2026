"""Format evaluation results as tables for the terminal and README."""

from __future__ import annotations

from tabulate import tabulate

from .metrics import EvalResult, HardNegativeResult


def format_technique_table(result: EvalResult) -> str:
    headers = ["Technique", "P", "R", "F1", "Support"]
    rows = []
    for m in sorted(result.technique_metrics.values(), key=lambda m: -m.support):
        if m.support == 0 and m.tp == 0 and m.fp == 0:
            continue
        rows.append([
            m.display_name,
            f"{m.precision:.3f}",
            f"{m.recall:.3f}",
            f"{m.f1:.3f}",
            m.support,
        ])
    rows.append(["---", "---", "---", "---", "---"])
    rows.append([
        "Micro avg",
        f"{result.micro_precision:.3f}",
        f"{result.micro_recall:.3f}",
        f"{result.micro_f1:.3f}",
        result.total_spans,
    ])
    rows.append([
        "Macro avg",
        "",
        "",
        f"{result.macro_f1:.3f}",
        "",
    ])
    return tabulate(rows, headers=headers, tablefmt="github")


def format_category_table(result: EvalResult) -> str:
    headers = ["Category", "P", "R", "F1", "Support"]
    rows = []
    for m in sorted(result.category_metrics.values(), key=lambda m: -m.support):
        if m.support == 0 and m.tp == 0 and m.fp == 0:
            continue
        rows.append([
            m.display_name,
            f"{m.precision:.3f}",
            f"{m.recall:.3f}",
            f"{m.f1:.3f}",
            m.support,
        ])
    return tabulate(rows, headers=headers, tablefmt="github")


def format_hard_negative_table(results: dict[str, HardNegativeResult]) -> str:
    headers = ["Hard-negative set", "Items", "FP", "FPR"]
    rows = []
    for r in results.values():
        rows.append([
            r.set_name,
            r.total_items,
            r.false_positives,
            f"{r.fpr:.3f}",
        ])
    return tabulate(rows, headers=headers, tablefmt="github")


def format_comparison_table(results: list[EvalResult]) -> str:
    headers = ["Model", "Micro P", "Micro R", "Micro F1", "Macro F1"]
    rows = []
    for r in results:
        rows.append([
            r.model_name,
            f"{r.micro_precision:.3f}",
            f"{r.micro_recall:.3f}",
            f"{r.micro_f1:.3f}",
            f"{r.macro_f1:.3f}",
        ])
    return tabulate(rows, headers=headers, tablefmt="github")


def format_full_report(
    results: list[EvalResult],
    hard_negatives: dict[str, HardNegativeResult] | None = None,
) -> str:
    parts = []
    parts.append("# Evaluation Report\n")

    if len(results) > 1:
        parts.append("## Model Comparison\n")
        parts.append(format_comparison_table(results))
        parts.append("")

    for r in results:
        parts.append(f"## {r.model_name or 'Model'}\n")
        parts.append("### Per-technique metrics\n")
        parts.append(format_technique_table(r))
        parts.append("")
        parts.append("### Per-category metrics\n")
        parts.append(format_category_table(r))
        parts.append("")

    if hard_negatives:
        parts.append("## Hard-negative false-positive rates\n")
        parts.append(format_hard_negative_table(hard_negatives))
        parts.append("")

    return "\n".join(parts)

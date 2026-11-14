"""Format evaluation results as tables for the terminal and the README."""

from __future__ import annotations

from tabulate import tabulate

from .labelled import HARD_NEGATIVE_SETS
from .metrics import BinaryMetrics, EvalResult


def _ci(ci: tuple[float, float]) -> str:
    return f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def _row(label: list[object], m: BinaryMetrics) -> list[object]:
    return [
        *label,
        f"{m.precision:.3f}",
        _ci(m.precision_ci),
        f"{m.recall:.3f}",
        _ci(m.recall_ci),
        f"{m.f1:.3f}",
        f"{m.fpr:.3f}",
        _ci(m.fpr_ci),
        m.total,
        f"{m.abstain_rate:.2f}",
        m.failed,
    ]


METRIC_HEADERS = [
    "P",
    "P 95% CI",
    "R",
    "R 95% CI",
    "F1",
    "FPR",
    "FPR 95% CI",
    "Scored",
    "Abstain",
    "Failed",
]


def format_dimension_table(result: EvalResult) -> str:
    rows = []
    for dim, dr in result.dimensions.items():
        rows.append([*_row([dim], dr.overall), dr.missing])
    return tabulate(rows, headers=["Dimension", *METRIC_HEADERS, "Missing"], tablefmt="github")


def format_hard_negative_table(result: EvalResult) -> str:
    headers = [
        "Dimension",
        "Hard-negative set",
        "FP",
        "Scored neg",
        "FPR",
        "FPR 95% CI",
        "Abstained",
        "Failed",
    ]
    rows = []
    for dim, dr in result.dimensions.items():
        for set_name in sorted(dr.per_set):
            if set_name not in HARD_NEGATIVE_SETS:
                continue
            m = dr.per_set[set_name]
            rows.append(
                [
                    dim,
                    set_name,
                    m.fp,
                    m.fp + m.tn,
                    f"{m.fpr:.3f}",
                    _ci(m.fpr_ci),
                    m.abstained,
                    m.failed,
                ]
            )
    if not rows:
        return "(no hard-negative results)"
    return tabulate(rows, headers=headers, tablefmt="github")


def format_language_table(result: EvalResult) -> str:
    rows = [
        _row([dim, lang], m)
        for dim, dr in result.dimensions.items()
        for lang, m in sorted(dr.per_language.items())
    ]
    if not rows:
        return "(no results)"
    return tabulate(rows, headers=["Dimension", "Language", *METRIC_HEADERS], tablefmt="github")


def format_calibration_table(result: EvalResult) -> str:
    headers = ["Dimension", "Bin", "Avg score", "Actual positive rate", "N"]
    rows = [
        [
            dim,
            f"[{b.bin_start:.1f}, {b.bin_end:.1f})",
            f"{b.predicted_positive:.3f}",
            f"{b.actual_positive:.3f}",
            b.count,
        ]
        for dim, dr in result.dimensions.items()
        for b in dr.calibration
    ]
    if not rows:
        return "(no calibration data)"
    return tabulate(rows, headers=headers, tablefmt="github")


def format_ablation_table(result: EvalResult) -> str:
    rows = []
    for dim, dr in result.dimensions.items():
        if not dr.ablation:
            continue
        rows.append(_row([dim, "(all families)"], dr.overall))
        rows.extend(
            _row([dim, f"without {family}"], m) for family, m in sorted(dr.ablation.items())
        )
    if not rows:
        return "(no ablation data: predictions were written without it)"
    return tabulate(rows, headers=["Dimension", "Variant", *METRIC_HEADERS], tablefmt="github")


def format_full_report(result: EvalResult) -> str:
    versions = ", ".join(result.pipeline_versions) or "unknown"
    parts = [
        "# Evaluation report\n",
        f"{result.total_items} labelled items, threshold {result.threshold}, pipeline {versions}. "
        "Abstain = finished analyses that said 'not enough evidence'; Failed = analyses that "
        "broke (not counted as abstentions); Missing = no prediction.\n",
        "## Per-dimension metrics\n",
        format_dimension_table(result),
        "",
        "## Hard-negative false-positive rates\n",
        format_hard_negative_table(result),
        "",
        "## Per language\n",
        format_language_table(result),
        "",
        "## Calibration (reliability)\n",
        format_calibration_table(result),
        "",
        "## Ablation (each family's evidence removed)\n",
        format_ablation_table(result),
        "",
    ]
    return "\n".join(parts)

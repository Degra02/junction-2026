"""Format evaluation results as tables for the terminal, README and metrics page."""

from __future__ import annotations

from tabulate import tabulate

from .labelled import HARD_NEGATIVE_SETS
from .metrics import BinaryMetrics, CalibrationBin, DimensionResult, EvalResult


def format_dimension_table(result: EvalResult) -> str:
    headers = ["Dimension", "P", "P 95% CI", "R", "F1", "FPR", "FPR 95% CI", "Abstain", "N"]
    rows = []
    for dim, dr in result.dimensions.items():
        m = dr.overall
        p_lo, p_hi = m.precision_ci
        fpr_lo, fpr_hi = m.fpr_ci
        rows.append([
            dim,
            f"{m.precision:.3f}",
            f"[{p_lo:.3f}, {p_hi:.3f}]",
            f"{m.recall:.3f}",
            f"{m.f1:.3f}",
            f"{m.fpr:.3f}",
            f"[{fpr_lo:.3f}, {fpr_hi:.3f}]",
            f"{m.abstain_rate:.2f}",
            m.total + m.abstained,
        ])
    return tabulate(rows, headers=headers, tablefmt="github")


def format_hard_negative_table(result: EvalResult) -> str:
    headers = ["Dimension", "Hard-negative set", "FP", "Total neg", "FPR"]
    rows = []
    for dim, dr in result.dimensions.items():
        for set_name in sorted(dr.per_set):
            if set_name not in HARD_NEGATIVE_SETS:
                continue
            m = dr.per_set[set_name]
            neg_total = m.fp + m.tn
            if neg_total == 0:
                continue
            rows.append([
                dim, set_name, m.fp, neg_total, f"{m.fpr:.3f}",
            ])
    if not rows:
        return "(no hard-negative results)"
    return tabulate(rows, headers=headers, tablefmt="github")


def format_calibration_table(result: EvalResult) -> str:
    headers = ["Dimension", "Bin", "Avg score", "Actual positive rate", "N"]
    rows = []
    for dim, bins in result.calibration.items():
        for b in bins:
            rows.append([
                dim,
                f"[{b.bin_start:.1f}, {b.bin_end:.1f})",
                f"{b.predicted_positive:.3f}",
                f"{b.actual_positive:.3f}",
                b.count,
            ])
    if not rows:
        return "(no calibration data)"
    return tabulate(rows, headers=headers, tablefmt="github")


def format_full_report(result: EvalResult) -> str:
    parts = [
        "# Evaluation Report\n",
        "## Per-dimension metrics\n",
        format_dimension_table(result),
        "",
        "## Hard-negative false-positive rates\n",
        format_hard_negative_table(result),
        "",
        "## Calibration (reliability)\n",
        format_calibration_table(result),
        "",
    ]
    return "\n".join(parts)

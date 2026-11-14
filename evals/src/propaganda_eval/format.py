"""Format evaluation results as tables for the terminal and the README.

`n/a` = empty denominator (no item to compute it on), never 0. Coverage columns read
"scored/labelled": recall is computed on the scored positives, FPR on the scored negatives;
"R all" counts abstained and failed positives as misses.
"""

from __future__ import annotations

from tabulate import tabulate

from .labelled import HARD_NEGATIVE_SETS
from .metrics import LABEL_SOURCE_FAMILY, SET_SOURCE_FAMILY, BinaryMetrics, EvalResult


def _f(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def _ci(ci: tuple[float, float] | None) -> str:
    return "n/a" if ci is None else f"[{ci[0]:.2f}, {ci[1]:.2f}]"


def _rate(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def _table(rows: list[list[object]], headers: list[str]) -> str:
    # disable_numparse: keep "0.000" and "n/a" as written instead of re-formatting numbers.
    return tabulate(rows, headers=headers, tablefmt="github", disable_numparse=True)


def _row(label: list[object], m: BinaryMetrics) -> list[object]:
    return [
        *label,
        _f(m.precision),
        _ci(m.precision_ci),
        f"{m.total}/{m.positives + m.negatives}",
        _f(m.recall),
        _ci(m.recall_ci),
        f"{m.tp + m.fn}/{m.positives}",
        _f(m.recall_all),
        _f(m.fpr),
        _ci(m.fpr_ci),
        f"{m.fp + m.tn}/{m.negatives}",
        _rate(m.abstain_rate),
        m.failed,
    ]


METRIC_HEADERS = [
    "P",
    "P 95% CI",
    "Scored",
    "R",
    "R 95% CI",
    "Pos scored",
    "R all",
    "FPR",
    "FPR 95% CI",
    "Neg scored",
    "Abstain",
    "Failed",
]


def format_dimension_table(result: EvalResult) -> str:
    rows = []
    for dim, dr in result.dimensions.items():
        rows.append([*_row([dim], dr.overall), dr.missing])
    return _table(rows, ["Dimension", *METRIC_HEADERS, "Missing"])


def format_headline_table(result: EvalResult) -> str:
    rows = []
    for dim, dr in result.dimensions.items():
        family = LABEL_SOURCE_FAMILY[dim]
        rows.append(_row([dim, "all families"], dr.overall))
        without = dr.ablation.get(family)
        rows.append(
            _row([dim, f"without {family}"], without)
            if without
            else [dim, f"without {family}", *["n/a"] * len(METRIC_HEADERS)]
        )
    for (dim, set_name), family in sorted(SET_SOURCE_FAMILY.items()):
        dr = result.dimensions.get(dim)
        if dr is None or set_name not in dr.per_set:
            continue
        rows.append(_row([f"{dim} on {set_name}", "all families"], dr.per_set[set_name]))
        without = dr.ablation_per_set.get(family, {}).get(set_name)
        if without:
            rows.append(_row([f"{dim} on {set_name}", f"without {family}"], without))
    table = _table(rows, ["Dimension", "Variant", *METRIC_HEADERS])
    fit_lines = []
    for dim, family in LABEL_SOURCE_FAMILY.items():
        fit = result.fit.get(dim)
        if not fit:
            fit_lines.append(f"- {dim}: no fit yet (prior weights), no cross-validated AUC.")
            continue
        ablation = fit.get("ablation") or {}
        report = ablation.get(family) if isinstance(ablation, dict) else None
        without = _f(report.get("auc_without")) if report else "n/a"
        alone = _f(report.get("auc_alone")) if report else "n/a"
        fit_lines.append(
            f"- {dim}: cross-validated AUC {_f(fit.get('auc'))} on n={fit.get('n')}; "
            f"refitted without {family} {without}; {family} alone {alone}."
        )
    return "\n".join([table, "", *fit_lines])


def format_hard_negative_table(result: EvalResult) -> str:
    headers = [
        "Dimension",
        "Hard-negative set",
        "FP",
        "Neg scored",
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
                    f"{m.fp + m.tn}/{m.negatives}",
                    _f(m.fpr),
                    _ci(m.fpr_ci),
                    m.abstained,
                    m.failed,
                ]
            )
    if not rows:
        return "(no hard-negative results)"
    return _table(rows, headers)


def format_language_table(result: EvalResult) -> str:
    rows = [
        _row([dim, lang], m)
        for dim, dr in result.dimensions.items()
        for lang, m in sorted(dr.per_language.items())
    ]
    if not rows:
        return "(no results)"
    return _table(rows, ["Dimension", "Language", *METRIC_HEADERS])


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
    return _table(rows, headers)


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
    return _table(rows, ["Dimension", "Variant", *METRIC_HEADERS])


def format_full_report(result: EvalResult) -> str:
    versions = ", ".join(result.pipeline_versions) or "unknown"
    parts = [
        "# Evaluation report\n",
        f"{result.total_items} labelled items, threshold {result.threshold}, pipeline {versions}. "
        "P, R and FPR are computed on the items that got a score: read them next to their "
        "coverage (Scored, Pos scored, Neg scored = scored/labelled). R all counts abstained and "
        "failed positives as misses. Abstain = finished analyses that said 'not enough "
        "evidence'; Failed = analyses that broke (not counted as abstentions); Missing = no "
        "prediction; n/a = nothing to compute it on.\n",
        "## Headline, with and without the label's own source\n",
        "known_networks reads the VIGINUM list that labels viginum_pravda; fact_checks reads the "
        "ClaimReview that defines a debunked claim; outlet_fact_checker (source_profile) fires "
        "on the fact-checkers of hard_fact_checks. The rows without them are the honest numbers; "
        "the ablation here re-scores with the same weights, the fit line refits without.\n",
        format_headline_table(result),
        "",
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

"""Symmetry check (plans/persuasion-analysis.md §6): does single-actor treat both sides alike?

    mise run eval -- symmetry                       # local API, evals/symmetry.jsonl
    mise run eval -- symmetry --api https://the4thlover.tech

`evals/symmetry.jsonl` holds pasted-text pairs, written by us: the same meme text and visual
description with only the political target swapped (party, person, stance). They are a probe,
not labels: neither side is "right". Both sides of a pair are submitted as `kind: text` with
`force=true`; the report gives |Δ single| per pair and its mean and maximum over the pairs
where both sides got a score. A pair where one side is scored and the other abstains is an
asymmetry too and is listed apart. A gap above `GAP` is a finding to fix (the rater prompt)
before the phase 2 PR. Rows go to `evals/results/symmetry.jsonl` (gitignored).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from .runner import submit

GAP = 0.1


@dataclass
class Pair:
    id: str
    swap: str
    a: str
    b: str


@dataclass
class Side:
    single: float | None = None  # None: abstained or failed
    abstained: bool = False
    error: str | None = None
    analysis_id: str | None = None


def load_pairs(path: Path) -> list[Pair]:
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            pairs.append(Pair(d["id"], d.get("swap", ""), d["a"], d["b"]))
    return pairs


def summarise(results: list[tuple[Pair, Side, Side]]) -> dict[str, object]:
    """Numbers only: per pair |Δ single|, and mean / max over the pairs scored on both sides."""
    rows = []
    deltas = []
    one_sided = []
    broken = []
    for pair, a, b in results:
        delta = None
        if a.error or b.error:
            broken.append(pair.id)
        elif a.single is not None and b.single is not None:
            delta = abs(a.single - b.single)
            deltas.append(delta)
        elif (a.single is None) != (b.single is None):
            one_sided.append(pair.id)
        rows.append(
            {
                "id": pair.id,
                "swap": pair.swap,
                "a": a.single,
                "b": b.single,
                "delta": None if delta is None else round(delta, 4),
                "analysis_ids": [a.analysis_id, b.analysis_id],
            }
        )
    return {
        "pairs": len(results),
        "scored_both": len(deltas),
        "mean_abs_delta": round(sum(deltas) / len(deltas), 4) if deltas else None,
        "max_abs_delta": round(max(deltas), 4) if deltas else None,
        "over_gap": [r["id"] for r in rows if r["delta"] is not None and r["delta"] > GAP],
        "one_side_abstained": one_sided,
        "failed": broken,
        "rows": rows,
    }


async def _side(client: httpx.AsyncClient, text: str, timeout: float) -> Side:
    analysis, error = await submit(client, {"kind": "text", "value": text}, timeout)
    if analysis is None or error is not None or analysis.scores is None:
        return Side(error=error or "no scores", analysis_id=str(analysis.id) if analysis else None)
    single = analysis.scores.single
    return Side(
        single=single.confidence,
        abstained=single.abstained,
        analysis_id=str(analysis.id),
    )


async def run(pairs: list[Pair], api: str, concurrency: int, timeout: float) -> dict[str, object]:
    gate = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(base_url=api, timeout=30.0) as client:

        async def one(text: str) -> Side:
            async with gate:
                return await _side(client, text, timeout)

        sides = await asyncio.gather(*(one(t) for p in pairs for t in (p.a, p.b)))
    results = [(p, sides[2 * i], sides[2 * i + 1]) for i, p in enumerate(pairs)]
    return summarise(results)


def format_report(summary: dict[str, object]) -> str:
    def f(x: object) -> str:
        return "n/a" if x is None else f"{x:.3f}"

    lines = [
        "| Pair | Swap | single A | single B | abs delta |",
        "|---|---|---|---|---|",
    ]
    for r in summary["rows"]:
        lines.append(f"| {r['id']} | {r['swap']} | {f(r['a'])} | {f(r['b'])} | {f(r['delta'])} |")
    lines += [
        "",
        f"{summary['scored_both']} of {summary['pairs']} pairs scored on both sides; "
        f"mean |delta| {f(summary['mean_abs_delta'])}, max {f(summary['max_abs_delta'])} "
        f"(gap to fix: > {GAP}).",
        f"Over the gap: {', '.join(summary['over_gap']) or 'none'}. "
        f"One side abstained: {', '.join(summary['one_side_abstained']) or 'none'}. "
        f"Failed: {', '.join(summary['failed']) or 'none'}.",
    ]
    return "\n".join(lines)

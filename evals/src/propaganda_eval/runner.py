"""Run every labelled item through a local API and write the harness and fit inputs.

    mise run eval -- run                         # all items, http://127.0.0.1:8080
    mise run eval -- run --only fcd_it_001 --api http://127.0.0.1:8080

Run it against a local API with the limits off (`deploy/README.md`, "Local"), never the VPS:

    RATE_LIMIT_PER_MINUTE=0 MAX_ANALYSES_PER_HOUR=0 MAX_CONCURRENT_ANALYSES=8 \
        MAX_CONCURRENT_INFERENCE=4 mise run dev

Each item is submitted with `POST /api/analyses?force=true`: `{"kind": "url"}` when it has a
URL (coordinated signals need the outlet domain, its tracking IDs and the VIGINUM check), else
`{"kind": "text"}`. The runner polls `GET /api/analyses/{id}` until it is done or failed.

Writes to `evals/results/` (gitignored), one line per item, appended as analyses finish:
- `predictions.jsonl` for `eval`: `scores.<dimension>` is the confidence, null when abstained.
  An analysis that failed, or finished with a failed step, is `"failed": true`: the pipeline
  broke, it did not abstain. `ablation` holds each dimension's confidence with one family's
  evidence removed, scored by `pipeline.score` with the current weights.
- `fit.jsonl` for `python -m pipeline.score.fit`: `{"analysis": <record>, "single": 0|1|null,
  "coordinated": 0|1|null}`, finished analyses only.

Items already in `predictions.jsonl` without a failure are skipped, so an interrupted run
resumes; `--fresh` starts over.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from pipeline.common.contracts import Analysis, AnalysisStatus, Family, StepState
from pipeline.score import run as score
from pipeline.score.families import COORDINATED, SINGLE

from .labelled import DATA, LabelledItem

# The API's `MAX_IMAGE_DATA_URI_CHARS` (api/src/routes/analyses.rs): a longer data URI is
# refused with 400, so the runner fails the item before sending it.
MAX_IMAGE_DATA_URI_CHARS = 450_000

FAMILIES = {"single": SINGLE, "coordinated": COORDINATED}
POLL_SECS = 2.0


@dataclass
class Outcome:
    item: LabelledItem
    analysis: Analysis | None
    error: str | None


def payload(item: LabelledItem) -> dict[str, str]:
    if item.image:
        return {"kind": "image", "value": image_data_uri(DATA / item.image)}
    if item.url:
        return {"kind": "url", "value": item.url}
    return {"kind": "text", "value": item.text}


def image_data_uri(path: Path) -> str:
    data = path.read_bytes()
    mime = image_mime(data)
    if mime is None:
        raise ValueError(f"{path.name}: not a JPEG, PNG, GIF or WebP image")
    uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    if len(uri) > MAX_IMAGE_DATA_URI_CHARS:
        raise ValueError(f"{path.name}: {len(uri)} characters as a data URI, over the API's limit")
    return uri


def image_mime(data: bytes) -> str | None:
    """From the file's first bytes, not its name: datasets save JPEGs as `.png`."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def failure(analysis: Analysis) -> str | None:
    """Why this analysis does not count as a pipeline result, or None when it does."""
    if analysis.status == AnalysisStatus.failed:
        return analysis.error or "the analysis failed"
    if analysis.scores is None:
        return "no scores"
    broken = [
        f"{s.name}: {s.error or 'failed'}" for s in analysis.steps if s.state == StepState.failed
    ]
    return "; ".join(broken) or None


def ablation(analysis: Analysis) -> dict[str, dict[str, float | None]]:
    """Per dimension, the confidence with one family's evidence removed."""
    out: dict[str, dict[str, float | None]] = {dim: {} for dim in FAMILIES}
    for dim, families in FAMILIES.items():
        for family in families:
            if not any(e.family == family for e in analysis.evidence):
                continue
            kept = [e for e in analysis.evidence if e.family != family]
            scores = score(analysis.model_copy(update={"evidence": kept})).scores
            out[dim][Family(family).value] = getattr(scores, dim).confidence
    return out


def prediction(item: LabelledItem, outcome: Outcome) -> dict[str, object]:
    a = outcome.analysis
    row: dict[str, object] = {
        "item_id": item.id,
        "analysis_id": str(a.id) if a else None,
        "pipeline_version": a.pipeline_version if a else "",
    }
    if outcome.error is not None or a is None or a.scores is None:
        return {**row, "failed": True, "error": outcome.error, "scores": {}}
    skipped = [s.name.value for s in a.steps if s.state == StepState.skipped]
    return {
        **row,
        "failed": False,
        "scores": {dim: getattr(a.scores, dim).confidence for dim in FAMILIES},
        "abstain_reasons": {dim: getattr(a.scores, dim).reason for dim in FAMILIES},
        "skipped_steps": skipped,
        "ablation": ablation(a),
    }


def fit_row(item: LabelledItem, analysis: Analysis) -> dict[str, object]:
    labels = {dim: None if v is None else int(v) for dim, v in item.labels.items()}
    return {"item_id": item.id, "analysis": analysis.model_dump(mode="json"), **labels}


async def analyse(client: httpx.AsyncClient, item: LabelledItem, timeout: float) -> Outcome:
    try:
        body = payload(item)
    except (OSError, ValueError) as e:  # missing or oversized image: the item fails, not the run
        return Outcome(item, None, f"input: {e}")
    analysis, error = await submit(client, body, timeout)
    return Outcome(item, analysis, error)


async def submit(
    client: httpx.AsyncClient, body: dict[str, str], timeout: float
) -> tuple[Analysis | None, str | None]:
    """Submit one input with `force=true` and poll it: the finished analysis and why it does
    not count as a pipeline result (None when it does)."""
    try:
        created = await client.post("/api/analyses", params={"force": "true"}, json=body)
        if created.status_code != 202:
            return None, f"submit: HTTP {created.status_code} {created.text[:200]}"
        analysis_id = created.json()["id"]
        deadline = time.monotonic() + timeout
        while True:
            response = await client.get(f"/api/analyses/{analysis_id}")
            response.raise_for_status()
            analysis = Analysis.model_validate(response.json())
            if analysis.status in (AnalysisStatus.done, AnalysisStatus.failed):
                return analysis, failure(analysis)
            if time.monotonic() > deadline:
                return analysis, f"still {analysis.status.value} after {timeout:.0f} s"
            await asyncio.sleep(POLL_SECS)
    except (httpx.HTTPError, ValueError) as e:
        return None, f"{type(e).__name__}: {e}"


def finished_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if not row.get("failed"):
                done.add(row["item_id"])
    return done


def _keep_finished(path: Path, keep: set[str]) -> None:
    """Drop rows of items that will run again (failed ones), so each item has one line."""
    if not path.exists():
        return
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line)["item_id"] in keep
    ]
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


async def run(
    items: list[LabelledItem],
    api: str,
    out_dir: Path,
    concurrency: int,
    timeout: float,
    fresh: bool,
) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = out_dir / "predictions.jsonl"
    fit_path = out_dir / "fit.jsonl"
    if fresh:
        predictions_path.unlink(missing_ok=True)
        fit_path.unlink(missing_ok=True)
    done = finished_ids(predictions_path)
    _keep_finished(predictions_path, done)
    _keep_finished(fit_path, done)
    todo = [i for i in items if i.id not in done]
    print(f"{len(todo)} to run, {len(done)} already done", flush=True)

    counts = {"done": 0, "failed": 0}
    gate = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(base_url=api, timeout=30.0) as client:

        async def one(item: LabelledItem) -> None:
            async with gate:
                outcome = await analyse(client, item, timeout)
            row = prediction(item, outcome)
            with predictions_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if row["failed"]:
                counts["failed"] += 1
                print(f"FAILED {item.id}: {outcome.error}", flush=True)
                return
            assert outcome.analysis is not None
            with fit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(fit_row(item, outcome.analysis), ensure_ascii=False) + "\n")
            counts["done"] += 1
            print(f"done   {item.id}: {row['scores']}", flush=True)

        await asyncio.gather(*(one(i) for i in todo))
    return counts

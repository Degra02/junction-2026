"""Stage worker: the Rust API calls `POST /stages/{name}` once per stage.

Contract: request body is the full `Analysis`; a 200 response is the stage's patch; 501 means
the stage is not implemented yet; any other status fails the step, and the `message` of its
error body is shown publicly as the step's error. Messages therefore never carry exception
text (it can contain request URLs with keys): only `StageError` messages pass through.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from pipeline.common import progress
from pipeline.common.contracts import Analysis, StageAvailability, StageName, WorkerHealth
from pipeline.common.errors import StageError
from worker import stages

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await run_in_threadpool(stages.warm_up)
    yield


app = FastAPI(title="Junction stage worker", lifespan=lifespan)


def _error(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message})


@app.get("/health")
def health() -> WorkerHealth:
    available = []
    for name, spec in stages.STAGES.items():
        loaded = stages.load(spec)
        available.append(
            StageAvailability(name=name, implemented=loaded.fn is not None, error=loaded.error)
        )
    return WorkerHealth(stages=available)


@app.get("/progress/{analysis_id}")
async def stage_progress(analysis_id: UUID) -> dict[str, str]:
    """Latest progress note of each stage running for the analysis (`pipeline.common.progress`)."""
    return progress.notes(str(analysis_id))


@app.post("/stages/{name}")
async def run_stage(name: StageName, analysis: Analysis) -> JSONResponse:
    spec = stages.STAGES[name]
    loaded = stages.load(spec)
    if loaded.error is not None:
        message = f"the stage failed to load ({loaded.error}); details are in the worker log"
        return _error(500, "import_failed", message)
    fn = loaded.fn
    if fn is None:
        return _error(501, "not_implemented", f"{spec.module}.{spec.function} does not exist yet")

    try:
        with progress.track(str(analysis.id), name.value):
            # Sync stages run in the threadpool so CPU-bound model calls never block the
            # event loop.
            result = (
                await fn(analysis) if stages.is_async(fn) else await run_in_threadpool(fn, analysis)
            )
    except StageError as e:
        log.warning("stage %s gave up: %s", name, e)
        return _error(422, "stage_failed", str(e))
    except Exception as e:
        log.exception("stage %s raised", name)
        message = f"the stage failed ({type(e).__name__}); details are in the worker log"
        return _error(500, "stage_failed", message)

    try:
        patch = (
            result
            if isinstance(result, spec.patch)
            else spec.patch.model_validate(
                result.model_dump() if isinstance(result, BaseModel) else result
            )
        )
    except ValidationError as e:
        log.error("stage %s returned an invalid %s: %s", name, spec.patch.__name__, e)
        # Field paths and rule names only: the offending values stay in the log.
        problems = "; ".join(
            f"{'.'.join(map(str, problem['loc']))}: {problem['msg']}" for problem in e.errors()[:5]
        )
        return _error(500, "invalid_patch", f"expected {spec.patch.__name__}: {problems}")
    return JSONResponse(content=patch.model_dump(mode="json"))

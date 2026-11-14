"""Stage worker: the Rust API calls `POST /stages/{name}` once per stage.

Contract: request body is the full `Analysis`; a 200 response is the stage's patch; 501 means
the stage is not implemented yet; any other status fails the step with the response text.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from pipeline.common.contracts import Analysis, StageAvailability, StageName, WorkerHealth
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
        try:
            implemented = stages.load(spec) is not None
        except Exception:
            implemented = False
        available.append(StageAvailability(name=name, implemented=implemented))
    return WorkerHealth(stages=available)


@app.post("/stages/{name}")
async def run_stage(name: StageName, analysis: Analysis) -> JSONResponse:
    spec = stages.STAGES[name]
    try:
        fn = stages.load(spec)
    except Exception as e:
        log.exception("stage %s failed to import", name)
        return _error(500, "import_failed", f"{type(e).__name__}: {e}")
    if fn is None:
        return _error(501, "not_implemented", f"{spec.module}.{spec.function} does not exist yet")

    try:
        # Sync stages run in the threadpool so CPU-bound model calls never block the event loop.
        result = (
            await fn(analysis) if stages.is_async(fn) else await run_in_threadpool(fn, analysis)
        )
    except Exception as e:
        log.exception("stage %s raised", name)
        return _error(500, "stage_failed", f"{type(e).__name__}: {e}")

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
        return _error(500, "invalid_patch", f"expected {spec.patch.__name__}: {e}")
    return JSONResponse(content=patch.model_dump(mode="json"))

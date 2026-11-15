"""Where each pipeline stage lives and what it must return.

A stage is a function `run(analysis: Analysis) -> <Patch>` (sync or async) in the owner's
package. Until the module or function exists the worker answers 501 and the API marks the step
"not implemented yet", so stages can land one by one.
"""

import importlib
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from pipeline.common.contracts import (
    Analysis,
    ExplainPatch,
    ExtractPatch,
    GraphPatch,
    RetrievePatch,
    ScorePatch,
    SignalsPatch,
    StageName,
    StoryPatch,
    UnderstandPatch,
)

log = logging.getLogger(__name__)

type StageFn = Callable[
    [Analysis], BaseModel | dict[str, Any] | Awaitable[BaseModel | dict[str, Any]]
]


@dataclass(frozen=True)
class StageSpec:
    module: str
    function: str
    patch: type[BaseModel]


@dataclass(frozen=True)
class Loaded:
    """Result of importing a stage, kept for the life of the process."""

    # None when the stage is not implemented yet or failed to import.
    fn: StageFn | None
    # Why the import failed, in words safe to show publicly; None otherwise.
    error: str | None = None


STAGES: dict[StageName, StageSpec] = {
    StageName.extract: StageSpec("pipeline.extract", "run", ExtractPatch),
    StageName.understand: StageSpec("pipeline.understand", "run", UnderstandPatch),
    StageName.retrieve: StageSpec("pipeline.retrieve", "run", RetrievePatch),
    StageName.story: StageSpec("pipeline.story", "run", StoryPatch),
    StageName.signals_single: StageSpec("pipeline.signals", "run_single", SignalsPatch),
    StageName.signals_coordinated: StageSpec("pipeline.signals", "run_coordinated", SignalsPatch),
    StageName.score: StageSpec("pipeline.score", "run", ScorePatch),
    StageName.explain: StageSpec("pipeline.explain", "run", ExplainPatch),
    StageName.graph: StageSpec("pipeline.graph", "run", GraphPatch),
}

_loaded: dict[StageSpec, Loaded] = {}


def load(spec: StageSpec) -> Loaded:
    """Import the stage once and remember the outcome.

    A failed import is not retried until the worker restarts: stage modules load models at
    import time, and importing again on every health check would load them again.
    """
    if spec not in _loaded:
        _loaded[spec] = _import(spec)
    return _loaded[spec]


def _import(spec: StageSpec) -> Loaded:
    try:
        module = importlib.import_module(spec.module)
    except ModuleNotFoundError as e:
        # Only "the stage package itself is missing" means not implemented; a missing
        # dependency inside an existing stage is a real error.
        if e.name is not None and (spec.module == e.name or spec.module.startswith(f"{e.name}.")):
            return Loaded(fn=None)
        log.exception("stage module %s failed to import", spec.module)
        return Loaded(fn=None, error=f"ModuleNotFoundError: {e.name}")
    except Exception as e:
        log.exception("stage module %s failed to import", spec.module)
        return Loaded(fn=None, error=type(e).__name__)
    fn = getattr(module, spec.function, None)
    return Loaded(fn=fn if callable(fn) else None)


def is_async(fn: StageFn) -> bool:
    return inspect.iscoroutinefunction(fn)


def warm_up() -> None:
    """Import every stage once at startup so models load before the first request."""
    for name, spec in STAGES.items():
        loaded = load(spec)
        if loaded.error is not None:
            log.error("stage %s failed to load (%s); its requests return 500", name, loaded.error)
        elif loaded.fn is None:
            log.info("stage %s: not implemented yet", name)

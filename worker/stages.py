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


STAGES: dict[StageName, StageSpec] = {
    StageName.extract: StageSpec("pipeline.extract", "run", ExtractPatch),
    StageName.understand: StageSpec("pipeline.understand", "run", UnderstandPatch),
    StageName.retrieve: StageSpec("pipeline.retrieve", "run", RetrievePatch),
    StageName.story: StageSpec("pipeline.story", "run", StoryPatch),
    StageName.signals_single: StageSpec("pipeline.signals", "run_single", SignalsPatch),
    StageName.signals_coordinated: StageSpec("pipeline.signals", "run_coordinated", SignalsPatch),
    StageName.score: StageSpec("pipeline.score", "run", ScorePatch),
    StageName.explain: StageSpec("pipeline.explain", "run", ExplainPatch),
}


def load(spec: StageSpec) -> StageFn | None:
    """The stage function, or None when its module or function does not exist yet.

    Any other import error is a bug in the stage and propagates.
    """
    try:
        module = importlib.import_module(spec.module)
    except ModuleNotFoundError as e:
        # Only "the stage package itself is missing" means not implemented; a missing
        # dependency inside an existing stage is a real error.
        if e.name is not None and spec.module.startswith(e.name):
            return None
        raise
    fn = getattr(module, spec.function, None)
    return fn if callable(fn) else None


def is_async(fn: StageFn) -> bool:
    return inspect.iscoroutinefunction(fn)


def warm_up() -> None:
    """Import every stage once at startup so models load before the first request."""
    for name, spec in STAGES.items():
        try:
            if load(spec) is None:
                log.info("stage %s: not implemented yet", name)
        except Exception:
            log.exception("stage %s failed to import; its requests will return 500", name)

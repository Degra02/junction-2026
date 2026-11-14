"""Stages 5a/5b, signals: evidence for the single-actor and the coordinated dimension.

`run_single` (`pipeline.signals.single`) computes techniques, tone vs peers, claim support,
fact-check matches and the source profile; `run_coordinated` (`pipeline.signals.coordinated`)
computes text reuse, timing, infrastructure and known networks. Both work from the record only
(no network I/O).

The stage functions are resolved lazily (PEP 562): the worker's start-up `getattr` imports the
module that loads the models, while tests of the model-free modules import without loading them.
"""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "run_single":
        from pipeline.signals.single import run_single

        return run_single
    if name == "run_coordinated":
        from pipeline.signals.coordinated import run_coordinated

        return run_coordinated
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""The source graph: outlets tied by what analyses observed (`plans/source-graph.md`).

- `run` (`pipeline.graph.stage`, resolved lazily via PEP 562 so model-free tests of `build` do
  not load the embedding model): the live pipeline stage returning `GraphPatch` (`L2`).
- `python -m pipeline.graph.build`: offline batch build writing `evals/graph.json`.
"""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "run":
        from pipeline.graph.stage import run

        return run
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

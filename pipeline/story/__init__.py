"""Stage 4b, story: which retrieved reports cover the same event as the analysed article.

For every context item `run` sets `similarity` (multilingual embeddings of headline and lead),
`in_story` and `story_reason` (`assign`). Tone and claim support ignore items with
`in_story = false`, so a report that only shares words with the article never counts as a peer.

`run` is resolved lazily (PEP 562), as in `pipeline.signals`: the worker's start-up `getattr`
imports `stage`, which loads the model, while tests of `assign` import without loading it.
"""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "run":
        from pipeline.story.stage import run

        return run
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

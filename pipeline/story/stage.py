"""`run`: the story stage function. Importing this module loads the embedding model."""

from pipeline.common import progress
from pipeline.common.contracts import Analysis, StoryPatch
from pipeline.story import model
from pipeline.story.assign import assign


def run(analysis: Analysis) -> StoryPatch:
    """Plain `def`: embedding is CPU-bound, so the worker runs it in a thread."""
    if analysis.context:
        progress.report(f"Comparing {len(analysis.context)} reports with the article")
    return assign(analysis, model.embed)

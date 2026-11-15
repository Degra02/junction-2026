"""`run`: the live source-graph stage (`POST /stages/graph`, `L2`).

Plain `def` (no network I/O): embeds headline + lead with `story.model.embed`, detects article
languages with `extract.language.detect_language`, and computes within-record ties via
`build.patch_for_analysis`.
"""

from pipeline.common import progress
from pipeline.common.contracts import Analysis, GraphPatch
from pipeline.extract.language import detect_language
from pipeline.graph.build import patch_for_analysis
from pipeline.story import model


def _detect(text: str) -> str | None:
    lang = detect_language([text])
    return lang.code if lang else None


def run(analysis: Analysis) -> GraphPatch:
    progress.report("Recording outlet and tracker links")
    return patch_for_analysis(analysis, model.embed, _detect)

"""Live progress notes from a running stage ("9 sources so far").

A stage calls `report(...)` as often as it likes; the API polls the worker once a second and
streams the latest note to the UI as the step's `detail`. Notes are live-only: the detail stored
with the finished step comes from the stage's patch.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

# (analysis id, stage name) of the stage running in this task or thread.
_running: ContextVar[tuple[str, str] | None] = ContextVar("running_stage", default=None)
_notes: dict[tuple[str, str], str] = {}


def report(note: str) -> None:
    """Publish a short plain-language note about the stage that is running now.

    Call it from the stage function itself or from asyncio tasks it starts; threads a stage
    starts on its own do not inherit the context, and the note is then ignored. Outside the
    worker (tests, notebooks) it does nothing.
    """
    key = _running.get()
    if key is not None:
        _notes[key] = note


@contextmanager
def track(analysis_id: str, stage: str) -> Iterator[None]:
    """Used by the worker around one stage call: routes `report` to that stage."""
    key = (analysis_id, stage)
    token = _running.set(key)
    try:
        yield
    finally:
        _running.reset(token)
        _notes.pop(key, None)


def notes(analysis_id: str) -> dict[str, str]:
    """Latest note of every stage currently running for the analysis, by stage name."""
    return {
        stage: note for (running, stage), note in list(_notes.items()) if running == analysis_id
    }

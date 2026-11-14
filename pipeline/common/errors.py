"""Errors a stage may raise on purpose."""


class StageError(Exception):
    """A stage failure whose message is shown to the user exactly as written.

    Raise it for problems the reader can understand or act on:
    `raise StageError("This language is not supported yet")`. The message ends up in the public
    analysis record, so it must be plain language and must never contain keys, request URLs or
    other internals.

    Every other exception is reported publicly by its type only ("the stage failed
    (TimeoutError)"); its message and traceback go to the worker log.
    """

"""A stage whose dependency is missing: must surface as a 500, not as "not implemented"."""

import definitely_not_installed_dependency  # noqa: F401


def run(analysis):
    raise AssertionError("unreachable")

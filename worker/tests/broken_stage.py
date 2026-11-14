"""A stage whose dependency is missing: must surface as a 500, not as "not implemented"."""

from worker.tests.fake_stages import BROKEN_IMPORTS

BROKEN_IMPORTS.append(1)

import definitely_not_installed_dependency  # noqa: E402, F401


def run(analysis):
    raise AssertionError("unreachable")

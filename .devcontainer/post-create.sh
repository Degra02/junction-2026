#!/usr/bin/env bash
# Runs once when the dev container is created. Mirrors docs/setup.md.
set -euo pipefail

# mise.toml loads .env; start from the template so mise does not choke on a missing file.
# Fill the real values from the team password manager.
if [ ! -f .env ]; then
	cp .env.example .env
	echo "post-create: created .env from .env.example — fill it in."
fi

mise trust
mise run setup
mise run check

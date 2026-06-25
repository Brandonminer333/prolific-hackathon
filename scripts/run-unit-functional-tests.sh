#!/usr/bin/env bash
# Run unit + functional tests using the project virtualenv when available.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Avoid updating tracked .pyc files during pre-commit (which fails the hook).
export PYTHONDONTWRITEBYTECODE=1

VENV_PYTEST="${ROOT}/.venv/bin/pytest"
if [[ -x "$VENV_PYTEST" ]]; then
  PYTEST="$VENV_PYTEST"
else
  PYTEST="$(command -v pytest)"
fi

exec "$PYTEST" -m "unit or functional" -p no:cacheprovider

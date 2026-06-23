#!/usr/bin/env bash
# Minimal CI entrypoint: apply the isolated environment, then run pytest.
# (pytest's --basetemp=./.ci/tmp self-wipes the sandbox each run.)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec "${PYBIN:-python3}" -m tools.env "$@"

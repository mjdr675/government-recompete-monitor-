"""Minimal environment layer: set the isolated execution env, nothing else.

One responsibility — point all temp at the repo-local sandbox and disable user
site-packages / .pyc pollution. No validation, no governor, no runtime checks.

Run as a module to apply the env and exec pytest (the CI entrypoint uses this):
    python -m tools.env [pytest args...]
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_TMP = str((REPO_ROOT / ".ci" / "tmp").resolve())

ENV = {
    "TMPDIR": _TMP,
    "TMP": _TMP,
    "TEMP": _TMP,
    "PYTHONNOUSERSITE": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}


def apply_env() -> None:
    """Set the isolated execution environment variables in this process."""
    os.makedirs(_TMP, exist_ok=True)
    os.environ.update(ENV)


if __name__ == "__main__":
    apply_env()
    os.execvp(sys.executable, [sys.executable, "-m", "pytest", *sys.argv[1:]])

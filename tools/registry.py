"""Tool Registry v1 — the single source of truth for external CLI detection.

Formalises tool detection (previously inline ``shutil.which`` calls and shell
``which``/``command -v`` fallbacks) into one cached, deterministic registry.

Design constraints:
  * ``shutil.which`` is the ONLY discovery mechanism — no shell calls.
  * No absolute paths are assumed or guessed; the only path returned is the one
    discovered on PATH, otherwise ``None``.
  * Behaviour is identical in CI, locally, and in production. The only variable
    is whether a tool exists on PATH.
"""
import shutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class Tool:
    name: str
    available: bool
    path: Optional[str]
    resolver: str


def resolve_tool(name: str) -> Tool:
    """Resolve a tool by name using PATH lookup only.

    Returns a :class:`Tool`. When found, ``available`` is True, ``path`` is the
    discovered executable and ``resolver`` is ``"which"``. When missing,
    ``available`` is False, ``path`` is ``None`` and ``resolver`` is
    ``"fallback"``.
    """
    path = shutil.which(name)

    if path:
        return Tool(name=name, available=True, path=path, resolver="which")

    return Tool(name=name, available=False, path=None, resolver="fallback")


class ToolRegistry:
    """Caches tool resolution so each tool is probed at most once.

    Deterministic and side-effect free: it only reads PATH via
    :func:`resolve_tool` and stores the result in an internal cache.
    """

    def __init__(self):
        self._cache: dict = {}

    def get(self, name: str) -> Tool:
        if name not in self._cache:
            self._cache[name] = resolve_tool(name)
        return self._cache[name]

    def available(self, name: str) -> bool:
        return self.get(name).available

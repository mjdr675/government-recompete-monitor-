"""Tool-layer package for Recompete.us.

Exposes a single global :class:`ToolRegistry` instance used across the codebase
to detect external CLI tools (e.g. ``ae``) portably, without hardcoded paths or
environment assumptions.
"""
from .registry import ToolRegistry

registry = ToolRegistry()

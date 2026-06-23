"""Tests for tools/registry.py — the Tool Registry.

Validate behaviour, not filesystem state, so they pass identically in CI,
locally, and in production.
"""
from tools.registry import Tool, ToolRegistry, resolve_tool

_MISSING = "definitely-not-a-real-tool-xyz"


def test_basic_resolution():
    # `python3` is guaranteed present wherever these tests run.
    tool = resolve_tool("python3")
    assert isinstance(tool, Tool)
    assert tool.name == "python3"
    assert tool.resolver in ("which", "fallback")
    # Probing a missing tool must not raise.
    missing = resolve_tool(_MISSING)
    assert missing.name == _MISSING


def test_missing_tool_behavior():
    tool = resolve_tool(_MISSING)
    assert tool.available is False
    assert tool.path is None
    assert tool.resolver == "fallback"


def test_present_tool_behavior():
    tool = resolve_tool("python3")
    assert tool.available is True
    assert tool.path is not None
    assert tool.resolver == "which"


def test_registry_caches():
    r = ToolRegistry()
    a = r.get("ae")
    b = r.get("ae")
    assert a is b


def test_registry_available_matches_get():
    r = ToolRegistry()
    assert r.available("python3") is r.get("python3").available
    assert r.available(_MISSING) is False

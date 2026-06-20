"""
LLM interface — Anthropic only for now.

Reads ANTHROPIC_API_KEY from environment. Never prints it.
Raises RuntimeError with a helpful message if key or package is missing.
"""

import os

_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 2048


def call(prompt: str, model: str = _DEFAULT_MODEL, max_tokens: int = _DEFAULT_MAX_TOKENS) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set.\n"
            "To set it for this session:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "Or add it to ai_agent/.env and run:\n"
            "  export $(grep -v '^#' ai_agent/.env | xargs)"
        )

    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def call_with_usage(
    prompt: str,
    model: str = _DEFAULT_MODEL,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> tuple[str, int, int]:
    """
    Like call(), but also returns (text, input_tokens, output_tokens).
    Use this to feed token counts into a BudgetTracker.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set.\n"
            "To set it for this session:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "Or add it to ai_agent/.env and run:\n"
            "  export $(grep -v '^#' ai_agent/.env | xargs)"
        )

    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return (
        message.content[0].text,
        message.usage.input_tokens,
        message.usage.output_tokens,
    )


def available() -> bool:
    """True if ANTHROPIC_API_KEY is set and anthropic is installed."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False

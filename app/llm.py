"""Thin wrapper around the Anthropic Messages API."""
import anthropic

from app import config

# 60s timeout so a hung request fails fast instead of blocking the worker.
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=60.0)


def generate(prompt: str, system: str | None = None) -> str:
    """Send one prompt to Claude and return the plain-text answer.

    Raises anthropic.APIError subclasses on failure; callers handle them.
    """
    kwargs = {
        "model": config.CHAT_MODEL,
        "max_tokens": config.MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    message = _client.messages.create(**kwargs)
    return "".join(block.text for block in message.content if block.type == "text")

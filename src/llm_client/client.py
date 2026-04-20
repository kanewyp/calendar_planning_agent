# =============================================================================
# src/llm_client/client.py — Anthropic Claude LLM wrapper
# =============================================================================
# Wraps all calls to the Anthropic API.  Provides two main functions:
#   - call_llm_json(): for prompts that must return structured JSON.
#   - call_llm_text(): for prompts that return free-form text.
#
# Implements retry logic (up to 2 retries) on parse failure or API error.
# Uses claude-sonnet-4-20250514 for all calls.
#
# STEPS TO COMPLETE:
# 1. Implement call_llm_json with JSON parsing and retry.
# 2. Implement call_llm_text for plain-text responses.
# 3. Implement the internal _call_anthropic helper.
# =============================================================================

from __future__ import annotations

import json
from typing import Any

import anthropic

from config.settings import settings

# Model to use for all LLM calls
MODEL_ID = "claude-sonnet-4-20250514"

# Maximum retries on parse failure or transient API error
MAX_RETRIES = 2


def _build_client() -> anthropic.Anthropic:
    """Instantiate the Anthropic client with the configured API key."""
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _call_anthropic(
    prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    """Low-level helper: send a single prompt to Claude and return the text.

    Args:
        prompt: The full prompt string.
        temperature: Sampling temperature (0.0 for deterministic).
        max_tokens: Maximum tokens in the response.

    Returns:
        The assistant's response text.

    STEPS:
    1. Build the client via _build_client().
    2. Call client.messages.create(
           model=MODEL_ID,
           max_tokens=max_tokens,
           temperature=temperature,
           messages=[{"role": "user", "content": prompt}],
       ).
    3. Extract and return response.content[0].text.
    4. Let API exceptions propagate — the caller handles retries.
    """
    client = _build_client()
    response = client.messages.create(
        model=MODEL_ID,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def call_llm_json(prompt: str, temperature: float = 0.0) -> Any:
    """Call the LLM with a prompt that expects a JSON response.

    Parses the response as JSON and retries up to MAX_RETRIES times
    if parsing fails or an API error occurs.

    Args:
        prompt: Prompt string instructing the model to return only JSON.
        temperature: Sampling temperature.

    Returns:
        Parsed Python object (list or dict).

    Raises:
        ValueError: If all retries are exhausted without a valid JSON response.

    STEPS:
    1. Attempt loop: for attempt in range(MAX_RETRIES + 1):
       a. Call _call_anthropic(prompt, temperature).
       b. Strip the response text of leading/trailing whitespace.
       c. Try json.loads(response_text).
       d. If successful, return the parsed object.
       e. If json.JSONDecodeError:
          - If this is not the last attempt, continue to next retry.
          - Optionally, append a note to the prompt like
            "Your previous response was not valid JSON. Return ONLY JSON."
       f. If anthropic.APIError:
          - If this is not the last attempt, continue to next retry.
    2. After all retries exhausted, raise ValueError with a descriptive message.
    """
    current_prompt = prompt
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response_text = _call_anthropic(current_prompt, temperature).strip()
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            last_error = e
            current_prompt = (
                f"{prompt}\n\n"
                "Your previous response was not valid JSON. Return ONLY JSON."
            )
        except anthropic.APIError as e:
            last_error = e
    raise ValueError(
        f"Failed to get valid JSON after {MAX_RETRIES + 1} attempts: {last_error}"
    )


def call_llm_text(prompt: str, temperature: float = 0.0) -> str:
    """Call the LLM with a prompt that expects a free-text response.

    Retries up to MAX_RETRIES times on API error.

    Args:
        prompt: Prompt string.
        temperature: Sampling temperature.

    Returns:
        The response text string.

    Raises:
        RuntimeError: If all retries are exhausted.

    STEPS:
    1. Attempt loop: for attempt in range(MAX_RETRIES + 1):
       a. Call _call_anthropic(prompt, temperature).
       b. If successful, return the text.
       c. If anthropic.APIError, retry.
    2. After all retries exhausted, raise RuntimeError.
    """
    pass  # TODO: implement

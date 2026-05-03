# =============================================================================
# src/llm_client/client.py — Configurable LLM wrapper
# =============================================================================
# All LLM calls in the app go through this module. It supports Anthropic,
# Gemini, generic OpenAI-compatible endpoints, and a deterministic mock mode.
# =============================================================================

from __future__ import annotations

import json
from typing import Any
from urllib import error, request

import anthropic
import google.auth
import google.auth.transport.requests

from config.settings import settings


ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-20250514"
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
VERTEX_OPENAI_BASE_URL_TEMPLATE = (
    "https://aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}"
    "/endpoints/openapi"
)

# Maximum retries on parse failure or transient provider error.
MAX_RETRIES = 2


def _normalize_provider(provider: str | None = None) -> str:
    return (provider or settings.LLM_PROVIDER or "anthropic").strip().lower()


def _model_for_purpose(provider: str, purpose: str) -> str:
    configured_model = (
        settings.LLM_RATIONALE_MODEL
        if purpose == "rationale"
        else settings.LLM_DECOMPOSITION_MODEL
    )
    if configured_model:
        return configured_model
    if provider in {"gemini", "vertex_ai"}:
        return GEMINI_DEFAULT_MODEL
    if provider == "anthropic":
        return ANTHROPIC_DEFAULT_MODEL
    if provider == "mock":
        return "mock"
    raise ValueError(
        "LLM model is not set. Configure LLM_DECOMPOSITION_MODEL and "
        "LLM_RATIONALE_MODEL, or use "
        "LLM_PROVIDER=gemini/vertex_ai/anthropic/mock defaults."
    )


def get_llm_metadata(purpose: str) -> dict[str, str]:
    """Return provider/model metadata for trace output without exposing secrets."""
    provider = _normalize_provider()
    return {
        "provider": provider,
        "model": _model_for_purpose(provider, purpose),
        "purpose": purpose,
    }


def _api_key_for_provider(provider: str) -> str:
    if provider == "anthropic":
        return settings.LLM_API_KEY or settings.ANTHROPIC_API_KEY
    if provider == "gemini":
        return settings.LLM_API_KEY or settings.GEMINI_API_KEY
    if provider == "vertex_ai":
        return _get_vertex_access_token()
    if provider == "openai_compatible":
        return settings.LLM_API_KEY
    if provider == "mock":
        return ""
    raise ValueError(
        f"Unsupported LLM_PROVIDER {provider!r}; expected one of "
        "'anthropic', 'gemini', 'vertex_ai', 'openai_compatible', or 'mock'"
    )


def _base_url_for_provider(provider: str) -> str:
    if provider == "gemini":
        return settings.LLM_BASE_URL or GEMINI_OPENAI_BASE_URL
    if provider == "vertex_ai":
        project_id = settings.VERTEX_PROJECT_ID
        if not project_id:
            raise ValueError("VERTEX_PROJECT_ID is required when LLM_PROVIDER=vertex_ai")
        return VERTEX_OPENAI_BASE_URL_TEMPLATE.format(
            project_id=project_id,
            location=settings.VERTEX_LOCATION or "global",
        )
    if provider == "openai_compatible":
        if not settings.LLM_BASE_URL:
            raise ValueError(
                "LLM_BASE_URL is required when LLM_PROVIDER=openai_compatible"
            )
        return settings.LLM_BASE_URL
    raise ValueError(f"Provider {provider!r} does not use an OpenAI-compatible URL")


def _build_anthropic_client(api_key: str) -> anthropic.Anthropic:
    if not api_key:
        raise ValueError(
            "LLM API key is not set. Set LLM_API_KEY or ANTHROPIC_API_KEY."
        )
    return anthropic.Anthropic(api_key=api_key)


def _get_vertex_access_token() -> str:
    """Return a Google Cloud access token using Application Default Credentials."""
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


def _call_anthropic(
    prompt: str,
    *,
    model: str,
    api_key: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    """Call Anthropic Messages API and return response text."""
    client = _build_anthropic_client(api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM provider request failed: HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"LLM provider request failed: {exc.reason}") from exc


def _extract_openai_compatible_text(response: Any) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"LLM provider returned an unexpected response shape: {response!r}"
        ) from exc

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in {None, "text"}
        ]
        return "".join(text_parts)
    raise RuntimeError(f"LLM provider returned non-text content: {content!r}")


def _call_openai_compatible(
    prompt: str,
    *,
    model: str,
    api_key: str,
    base_url: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    """Call an OpenAI-compatible Chat Completions endpoint."""
    if not api_key:
        raise ValueError("LLM API key is not set. Set LLM_API_KEY.")

    url = f"{base_url.rstrip('/')}/chat/completions"
    response = _post_json(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    )
    return _extract_openai_compatible_text(response)


def _call_mock(prompt: str, *, purpose: str) -> str:
    """Return deterministic local LLM responses for mock-mode walkthroughs."""
    _ = prompt
    if purpose == "rationale":
        return (
            "This strategy uses the available work blocks according to its "
            "scheduling rule while keeping all proposed events visible for review."
        )
    return json.dumps(
        [
            {
                "name": "Clarify goal requirements",
                "description": "Define the expected outcome and collect the key constraints.",
                "duration_minutes": 45,
            },
            {
                "name": "Complete focused work session",
                "description": "Make concrete progress on the most important part of the goal.",
                "duration_minutes": 60,
            },
            {
                "name": "Review and polish result",
                "description": "Check the work against the goal and make final adjustments.",
                "duration_minutes": 45,
            },
        ]
    )


def _call_llm(
    prompt: str,
    *,
    purpose: str,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> str:
    provider = _normalize_provider()
    model = _model_for_purpose(provider, purpose)
    api_key = _api_key_for_provider(provider)

    if provider == "anthropic":
        return _call_anthropic(
            prompt,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider in {"gemini", "vertex_ai", "openai_compatible"}:
        return _call_openai_compatible(
            prompt,
            model=model,
            api_key=api_key,
            base_url=_base_url_for_provider(provider),
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == "mock":
        return _call_mock(prompt, purpose=purpose)

    raise ValueError(f"Unsupported LLM_PROVIDER {provider!r}")


def call_llm_json(
    prompt: str,
    temperature: float = 0.0,
    purpose: str = "decomposition",
) -> Any:
    """Call an LLM for a JSON response and parse it."""
    current_prompt = prompt
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response_text = _call_llm(
                current_prompt,
                purpose=purpose,
                temperature=temperature,
            ).strip()
            return json.loads(response_text)
        except json.JSONDecodeError as exc:
            last_error = exc
            current_prompt = (
                f"{prompt}\n\n"
                "Your previous response was not valid JSON. Return ONLY JSON."
            )
        except anthropic.APIError as exc:
            last_error = exc
        except RuntimeError as exc:
            last_error = exc
    raise ValueError(
        f"Failed to get valid JSON after {MAX_RETRIES + 1} attempts: {last_error}"
    )


def call_llm_text(
    prompt: str,
    temperature: float = 0.0,
    purpose: str = "rationale",
) -> str:
    """Call an LLM for free-form text."""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return _call_llm(
                prompt,
                purpose=purpose,
                temperature=temperature,
            )
        except (anthropic.APIError, RuntimeError) as exc:
            last_error = exc
    raise RuntimeError(
        f"LLM call failed after {MAX_RETRIES + 1} attempts: {last_error}"
    )

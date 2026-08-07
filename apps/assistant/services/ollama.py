from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from django.conf import settings

from .schemas import validate_model_output

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
MAX_PROMPT_TEXT_LENGTH = 2000


class OllamaUnavailableError(Exception):
    pass


class MalformedOutputError(Exception):
    pass


def _sanitize_text(value: Any) -> str:
    text = str(value)[:MAX_PROMPT_TEXT_LENGTH]
    return "".join(ch for ch in text if ch not in "\x00\r")


def build_system_prompt(
    *,
    persona: str,
    intent: str,
    tools: list[dict[str, Any]],
    ui_context: dict[str, Any] | None,
    language: str,
) -> str:
    """Assemble the system prompt for the current turn.

    No credentials, no tool schemas beyond the current intent's set (FR-020),
    and no data outside the guest's view ever reach the prompt (FR-008/FR-015).
    """
    lines: list[str] = [
        "You are the TableMate restaurant guest assistant.",
        "Answer only from the live data and tools provided; never invent facts.",
        "Refuse politely anything outside the restaurant context, and never discuss",
        "other guests' reservations, staff-only data, or payment details.",
        f"Conversation language: {language}. Reply in this language.",
        f"Current intent: {intent}.",
        f"Persona: {persona}.",
    ]
    if tools:
        lines.append("Available tools this turn (strict JSON, exact names/arguments):")
        for tool in tools:
            desc = tool.get("description", "")
            schema = json.dumps(tool.get("schema", {}), ensure_ascii=False)
            lines.append(f"- {tool['name']}: {desc} {schema}")
    if ui_context:
        lines.append(
            f"UI context (client-visible view state): {_sanitize_text(json.dumps(ui_context, ensure_ascii=False))}"
        )
    lines.append(
        'You MUST respond with exactly one JSON object: '
        '{"kind": "reply", "text": "..."} or '
        '{"kind": "tool_call", "tool": "<tool name>", "arguments": {...}}. No other text.'
    )
    return "\n".join(lines)


def build_chat_messages(
    *,
    system_prompt: str,
    history: list[dict[str, str]],
    latest_user_text: str,
    tool_output: str | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": _sanitize_text(latest_user_text)})
    if tool_output:
        messages.append(
            {
                "role": "system",
                "content": f"The read-only tool returned:\n{_sanitize_text(tool_output)}\n"
                "Summarize the answer to the guest.",
            }
        )
    return messages


async def achat(*, messages: list[dict[str, str]], model: str, url: str) -> dict[str, Any]:
    """Call Ollama's /api/chat with JSON mode enabled; returns parsed JSON."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.2},
    }
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(f"{url.rstrip('/')}/api/chat", json=payload)
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            raise OllamaUnavailableError(f"Ollama request failed: {exc}") from exc

    try:
        content = response.json()["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MalformedOutputError(f"Unparsable model output: {exc}") from exc

    if not isinstance(parsed, dict):
        raise MalformedOutputError("Model output is not a JSON object.")
    return parsed


def chat(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(achat(*args, **kwargs))


async def generate_envelope(
    *,
    system_prompt: str,
    messages: list[dict[str, str]],
    model: str,
    url: str,
) -> dict[str, Any]:
    """One model turn with a single re-prompt on malformed output (FR-018).

    Returns a validated envelope (``reply`` or ``tool_call``). Raises
    ``MalformedOutputError`` after the re-prompt, ``OllamaUnavailableError``
    when the model cannot be reached.
    """
    parsed = await achat(messages=messages, model=model, url=url)
    try:
        return validate_model_output(parsed)
    except Exception as first_error:
        logger.warning("Model output rejected (%s); re-prompting once.", first_error)
        retry_messages = messages + [
            {
                "role": "system",
                "content": "Your previous response was invalid. Respond again with exactly one JSON "
                'object: {"kind":"reply","text":"..."} or {"kind":"tool_call","tool":"<name>","arguments":{...}}. '
                "No extra text or markdown.",
            }
        ]
        retry = await achat(messages=retry_messages, model=model, url=url)
        try:
            return validate_model_output(retry)
        except Exception as second_error:
            raise MalformedOutputError(f"Model output rejected twice: {second_error}") from second_error


def default_model() -> str:
    return str(getattr(settings, "ASSISTANT_OLLAMA_MODEL", "qwen2.5:7b"))


def default_url() -> str:
    return str(getattr(settings, "ASSISTANT_OLLAMA_URL", "http://llm-service:11434"))


__all__ = [
    "MalformedOutputError",
    "OllamaUnavailableError",
    "achat",
    "build_chat_messages",
    "build_system_prompt",
    "chat",
    "default_model",
    "default_url",
    "generate_envelope",
]

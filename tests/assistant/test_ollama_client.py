# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from apps.assistant.services import ollama
from apps.assistant.services.ollama import (
    MalformedOutputError,
    OllamaUnavailableError,
    achat,
    build_system_prompt,
    generate_envelope,
)

_BASE_PROMPT_KWARGS: dict[str, Any] = {
    "persona": "guest",
    "intent": "info",
    "tools": [{"name": "get_menu", "description": "menu", "schema": {"type": "object"}}],
    "language": "en",
}


def test_build_system_prompt_never_contains_credentials() -> None:
    prompt = build_system_prompt(**_BASE_PROMPT_KWARGS, ui_context=None)
    for secret in ("token", "authorization", "bearer", "password", "secret", "api_key", "llm-service:11434"):
        assert secret not in prompt.lower()


def test_build_system_prompt_includes_ui_context() -> None:
    prompt = build_system_prompt(
        **_BASE_PROMPT_KWARGS,
        ui_context={"active_view": "menu", "cart_item_count": 3},
    )
    assert "menu" in prompt
    assert "cart_item_count" in prompt


class TestAchat:
    @pytest.mark.asyncio
    async def test_valid_json_accepted(self, monkeypatch: Any) -> None:
        async def _fake_post(self: Any, url: str, **kwargs: Any) -> Any:
            class _Response:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict[str, Any]:
                    return {"message": {"content": '{"kind": "reply", "text": "hi"}'}}

            return _Response()

        monkeypatch.setattr("httpx.AsyncClient.post", _fake_post)
        parsed = await achat(messages=[{"role": "user", "content": "hi"}], model="m", url="http://llm")
        assert parsed == {"kind": "reply", "text": "hi"}

    @pytest.mark.asyncio
    async def test_unparsable_output_raises(self, monkeypatch: Any) -> None:
        async def _fake_post(self: Any, url: str, **kwargs: Any) -> Any:
            class _Response:
                def raise_for_status(self) -> None:
                    return None

                def json(self) -> dict[str, Any]:
                    return {"message": {"content": "not json"}}

            return _Response()

        monkeypatch.setattr("httpx.AsyncClient.post", _fake_post)
        with pytest.raises(MalformedOutputError):
            await achat(messages=[], model="m", url="http://llm")

    @pytest.mark.asyncio
    async def test_unreachable_raises_unavailable(self, monkeypatch: Any) -> None:
        async def _boom(self: Any, url: str, **kwargs: Any) -> Any:
            import httpx

            raise httpx.ConnectError("down")

        monkeypatch.setattr("httpx.AsyncClient.post", _boom)
        with pytest.raises(OllamaUnavailableError):
            await achat(messages=[], model="m", url="http://llm")


class TestGenerateEnvelope:
    @pytest.mark.asyncio
    async def test_valid_envelope_passes_through(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(
            ollama,
            "achat",
            AsyncMock(return_value={"kind": "tool_call", "tool": "get_menu", "arguments": {"query": "pasta"}}),
        )
        envelope = await generate_envelope(system_prompt="s", messages=[], model="m", url="u")
        assert envelope["kind"] == "tool_call"
        assert envelope["tool"] == "get_menu"

    @pytest.mark.asyncio
    async def test_out_of_schema_rejected_then_reprompted(self, monkeypatch: Any) -> None:
        calls: list[Any] = []

        async def _fake_achat(**kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            if len(calls) == 1:
                return {"kind": "surprise"}  # invalid first attempt
            return {"kind": "reply", "text": "ok"}  # valid after re-prompt

        monkeypatch.setattr(ollama, "achat", _fake_achat)
        envelope = await generate_envelope(
            system_prompt="s", messages=[{"role": "user", "content": "x"}], model="m", url="u"
        )
        assert envelope == {"kind": "reply", "text": "ok"}
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_double_malformed_raises(self, monkeypatch: Any) -> None:
        async def _fake_achat(**kwargs: Any) -> dict[str, Any]:
            return {"kind": 42}

        monkeypatch.setattr(ollama, "achat", _fake_achat)
        with pytest.raises(MalformedOutputError):
            await generate_envelope(system_prompt="s", messages=[], model="m", url="u")

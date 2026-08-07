# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from typing import Any

import pytest
from rest_framework import serializers

from apps.assistant.services.registry import (
    INTENT_INFO,
    PERSONA_ADMIN,
    PERSONA_GUEST,
    ExecutionResult,
    Tool,
    ToolContext,
    ToolResult,
    registry,
)

pytestmark = pytest.mark.django_db


class _EchoArgs(serializers.Serializer):
    value = serializers.CharField()


def _echo_executor(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    return ToolResult(text=f"echo:{args.get('value')}")


def _echo_execute(ctx: ToolContext, args: dict[str, Any]) -> ExecutionResult:
    return ExecutionResult(outcome="success", reference_id="ref-1")


class TestExtensionMechanism:
    def test_adding_a_tool_does_not_touch_existing_assistants(self, monkeypatch: Any) -> None:
        before = set(registry.names())
        assert "echo_test_tool" not in before
        assert len(before) >= 7

        tool = Tool(
            name="echo_test_tool",
            description="echo",
            schema=_EchoArgs,
            needs_confirmation=False,
            executor=_echo_executor,
            personas={PERSONA_GUEST},
        )
        monkeypatch.setattr(registry, "_tools", {**registry._tools, tool.name: tool})
        try:
            assert "echo_test_tool" in registry.names()
            assert before <= registry.names()  # existing tools untouched
            result = registry.get("echo_test_tool").executor(
                ToolContext(restaurant_id=1, owner=_fake_owner()), {"value": "x"}
            )
            assert result.text == "echo:x"
            # Existing assistants still expose exactly their old tool sets.
            assert registry.tools_for_intent(INTENT_INFO, PERSONA_GUEST) == [
                "get_menu",
                "get_restaurant_info",
                "check_availability",
            ]
        finally:
            monkeypatch.undo()

    def test_guest_persona_denied_admin_tool_regardless_of_intent(self) -> None:
        assert registry.is_allowed("get_floor_status", PERSONA_GUEST) is False
        offered = registry.tools_for_intent(INTENT_INFO, PERSONA_GUEST)
        assert "get_floor_status" not in offered

    def test_admin_persona_binds_floor_tool(self) -> None:
        assert registry.is_allowed("get_floor_status", PERSONA_ADMIN) is True

    def test_write_tool_can_carry_an_execute_closure(self) -> None:
        tool = Tool(
            name="write_echo",
            description="write echo",
            schema=_EchoArgs,
            needs_confirmation=True,
            executor=_echo_executor,
            execute=_echo_execute,
            personas={PERSONA_GUEST},
        )
        ctx = ToolContext(restaurant_id=1, owner=_fake_owner())
        result = tool.execute(ctx, {"value": "y"})
        assert result.outcome == "success"
        assert result.reference_id == "ref-1"


def _fake_owner() -> Any:
    from apps.assistant.services.identity import OwnerIdentity

    return OwnerIdentity(user=None, guest_key="guest:registry")

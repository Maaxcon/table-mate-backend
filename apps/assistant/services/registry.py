from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from rest_framework import serializers

from apps.authentication.models import RoleCode

if TYPE_CHECKING:
    from apps.authentication.models import User

    from .identity import OwnerIdentity

PERSONA_GUEST = "guest"
PERSONA_ADMIN = "admin"

INTENT_INFO = "info"
INTENT_BOOKING = "booking"
INTENT_CART = "cart"
INTENT_NONE = "none"

ALL_INTENTS: tuple[str, ...] = (INTENT_INFO, INTENT_BOOKING, INTENT_CART, INTENT_NONE)

# Data-driven category -> tool mapping (FR-014): adding an intent requires no
# rewrite of the router — it reads straight from this table.
INTENT_TOOLS: dict[str, list[str]] = {
    INTENT_INFO: ["get_menu", "get_restaurant_info", "check_availability"],
    INTENT_BOOKING: ["check_availability", "create_reservation", "reschedule_reservation", "cancel_reservation"],
    INTENT_CART: ["get_menu", "add_to_cart"],
    INTENT_NONE: [],
}

_GUEST_TOOLS: set[str] = {
    "get_menu",
    "get_restaurant_info",
    "check_availability",
    "create_reservation",
    "reschedule_reservation",
    "cancel_reservation",
    "add_to_cart",
}

# Demo admin persona (US-6): role-bounded tool set, strictly server-side.
PERSONA_TOOLS: dict[str, set[str]] = {
    PERSONA_GUEST: _GUEST_TOOLS,
    PERSONA_ADMIN: _GUEST_TOOLS | {"get_floor_status"},
}

ADMIN_ONLY_TOOLS: frozenset[str] = frozenset({"get_floor_status"})


def persona_for_role(role: str) -> str:
    if role == RoleCode.ADMIN:
        return PERSONA_ADMIN
    return PERSONA_GUEST


@dataclass(frozen=True)
class ToolContext:
    """Everything an executor needs to operate under the guest's identity."""

    restaurant_id: int
    owner: OwnerIdentity
    user: User | None = None
    guest_key: str = ""
    conversation_id: str = ""
    language: str = "en"
    cart_session_id: str | None = None
    now: Any = None

    def __post_init__(self) -> None:
        if self.user is None and self.owner.user is not None:
            object.__setattr__(self, "user", self.owner.user)
        if not self.guest_key and self.owner.guest_key:
            object.__setattr__(self, "guest_key", self.owner.guest_key)


@dataclass
class ToolResult:
    """Executor output: either a read-only result or a write proposal."""

    text: str | None = None
    summary: str | None = None
    consequence: str = ""
    needs_confirmation: bool = False
    # When set, the tool needs more info before it can propose (US-3/AS-4):
    # the pipeline replies with this question instead of creating a proposal.
    clarification: str | None = None


ToolExecutor = Callable[[ToolContext, dict[str, Any]], ToolResult]


@dataclass
class ExecutionResult:
    """Result of executing a confirmed write tool (FR-006)."""

    outcome: str
    reference_id: str | None = None
    error_code: str = ""


ToolExecution = Callable[[ToolContext, dict[str, Any]], ExecutionResult]


@dataclass
class Tool:
    name: str
    description: str
    schema: type[serializers.Serializer]
    needs_confirmation: bool
    executor: ToolExecutor
    execute: ToolExecution | None = None
    personas: set[str] = field(default_factory=set)

    def allowed_for(self, persona: str) -> bool:
        return persona in self.personas


class ToolRegistry:
    _tools: ClassVar[dict[str, Tool]] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def register_tool(
        self,
        name: str,
        description: str,
        schema: type[serializers.Serializer],
        *,
        needs_confirmation: bool,
        personas: set[str],
        execute: ToolExecution | None = None,
    ) -> Callable[[ToolExecutor], ToolExecutor]:
        def _wrap(executor: ToolExecutor) -> ToolExecutor:
            self.register(
                Tool(
                    name=name,
                    description=description,
                    schema=schema,
                    needs_confirmation=needs_confirmation,
                    executor=executor,
                    execute=execute,
                    personas=personas,
                )
            )
            return executor

        return _wrap

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schema_for(self, name: str) -> type[serializers.Serializer] | None:
        tool = self._tools.get(name)
        return tool.schema if tool is not None else None

    def names(self) -> set[str]:
        return set(self._tools)

    def tools_for_persona(self, persona: str) -> set[str]:
        allowed = PERSONA_TOOLS.get(persona, set())
        return {name for name, tool in self._tools.items() if name in allowed and persona in tool.personas}

    def tools_for_intent(self, intent: str, persona: str) -> list[str]:
        candidate = INTENT_TOOLS.get(intent, [])
        allowed = self.tools_for_persona(persona)
        return [name for name in candidate if name in allowed]

    def is_allowed(self, tool: str, persona: str) -> bool:
        registered = self._tools.get(tool)
        if registered is None:
            return False
        return persona in registered.personas and tool in PERSONA_TOOLS.get(persona, set())


registry = ToolRegistry()

__all__ = [
    "ADMIN_ONLY_TOOLS",
    "ALL_INTENTS",
    "INTENT_BOOKING",
    "INTENT_CART",
    "INTENT_INFO",
    "INTENT_NONE",
    "INTENT_TOOLS",
    "PERSONA_ADMIN",
    "PERSONA_GUEST",
    "PERSONA_TOOLS",
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "ExecutionResult",
    "persona_for_role",
    "registry",
]

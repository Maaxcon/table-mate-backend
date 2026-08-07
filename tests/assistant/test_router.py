# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from typing import Any

from apps.assistant.services.registry import (
    ALL_INTENTS,
    INTENT_BOOKING,
    INTENT_CART,
    INTENT_INFO,
    INTENT_NONE,
    PERSONA_ADMIN,
    PERSONA_GUEST,
    registry,
)
from apps.assistant.services.router import categorize


def _tools_for(text: str, persona: str = PERSONA_GUEST) -> list[str]:
    return registry.tools_for_intent(categorize(text), persona)


class TestIntentCategorize:
    def test_booking_intent_english(self) -> None:
        assert categorize("I want to book a table for 4 tonight at 7") == INTENT_BOOKING

    def test_booking_intent_ukrainian(self) -> None:
        assert categorize("забронюйте столик на 4 гостей") == INTENT_BOOKING

    def test_cart_intent(self) -> None:
        assert categorize("add the steak to my cart") == INTENT_CART

    def test_cart_intent_ukrainian(self) -> None:
        assert categorize("додай до кошика стейк") == INTENT_CART

    def test_info_intent(self) -> None:
        assert categorize("does the risotto contain gluten?") == INTENT_INFO

    def test_info_hours_intent(self) -> None:
        assert categorize("what are your opening hours?") == INTENT_INFO

    def test_none_for_greeting(self) -> None:
        assert categorize("hi, how are you?") == INTENT_NONE

    def test_none_for_empty(self) -> None:
        assert categorize("") == INTENT_NONE
        assert categorize(None) == INTENT_NONE


class TestFocusedToolSet:
    def test_info_yields_focused_read_only_set(self) -> None:
        tools = _tools_for("what allergens are in the pasta?")
        assert tools == ["get_menu", "get_restaurant_info", "check_availability"]
        assert len(tools) <= 5

    def test_booking_yields_booking_set(self) -> None:
        tools = _tools_for("book a table for 2 at 8pm")
        assert set(tools) == {
            "check_availability",
            "create_reservation",
            "reschedule_reservation",
            "cancel_reservation",
        }
        assert len(tools) <= 5

    def test_cart_yields_cart_set(self) -> None:
        tools = _tools_for("add soup and bread to my order")
        assert set(tools) == {"get_menu", "add_to_cart"}
        assert len(tools) <= 5

    def test_none_yields_no_tools(self) -> None:
        assert _tools_for("hello there") == []

    def test_guest_cannot_see_admin_tool_through_any_intent(self) -> None:
        for intent in ALL_INTENTS:
            offered = registry.tools_for_intent(intent, PERSONA_GUEST)
            assert "get_floor_status" not in offered

    def test_admin_persona_gets_floor_tool(self) -> None:
        tools = registry.tools_for_persona(PERSONA_ADMIN)
        assert "get_floor_status" in tools

    def test_guest_denied_admin_tool_server_side(self) -> None:
        assert registry.is_allowed("get_floor_status", PERSONA_GUEST) is False
        assert registry.is_allowed("get_floor_status", PERSONA_ADMIN) is True

    def test_unknown_tool_never_allowed(self) -> None:
        assert registry.is_allowed("does_not_exist", PERSONA_ADMIN) is False


class TestCategorizeAny:
    def test_categorize_returns_registered_intent(self, monkeypatch: Any) -> None:
        for text in ["book", "add to cart", "hours", "bye"]:
            assert categorize(text) in ALL_INTENTS

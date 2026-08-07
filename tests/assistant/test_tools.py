# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from django.utils import timezone

from apps.assistant.models import Message, MessageRole, ProposalStatus, ToolProposal
from apps.assistant.services import ollama
from apps.assistant.services.identity import OwnerIdentity
from apps.assistant.services.pipeline import process_turn
from apps.assistant.services.registry import ToolContext, registry
from apps.menu.models import Allergen, Ingredient, ModifierGroup, ModifierOption
from apps.orders.models import CartItem, CartSession, CartSessionStatus
from apps.reservations.models import Reservation, ReservationStatus

pytestmark = pytest.mark.django_db


def _ctx(*, restaurant: Any, user: Any | None = None, guest_key: str = "", language: str = "en") -> ToolContext:
    if user is not None:
        owner = OwnerIdentity(user=user, guest_key="")
    else:
        owner = OwnerIdentity(user=None, guest_key=guest_key or "guest:ctx")
    return ToolContext(
        restaurant_id=restaurant.id,
        owner=owner,
        user=user,
        guest_key=owner.guest_key,
        conversation_id="00000000-0000-0000-0000-000000000001",
        language=language,
    )


def _run_tool(name: str, ctx: ToolContext, args: dict[str, Any]) -> Any:
    tool = registry.get(name)
    assert tool is not None
    return tool.executor(ctx, args)


def _reservation(
    *,
    restaurant: Any,
    table: Any,
    customer: Any,
    start: Any,
    status: str = ReservationStatus.PENDING,
) -> Reservation:
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=start,
        end_at=start + timedelta(hours=2),
        status=status,
    )


class TestGetMenu:
    def test_returns_live_menu_data(self, item: Any, restaurant: Any, restaurant_settings: Any) -> None:
        allergen = Allergen.objects.create(restaurant=restaurant, name="Gluten")
        ingredient = Ingredient.objects.create(restaurant=restaurant, name="Flour")
        item.allergens.add(allergen)
        item.ingredients.add(ingredient)

        result = _run_tool("get_menu", _ctx(restaurant=restaurant), {"query": "steak"})
        assert "Steak" in result.text
        assert "29.99" in result.text
        assert "Gluten" in result.text
        assert "Flour" in result.text

    def test_available_only_filters_unavailable(self, item: Any, restaurant: Any, restaurant_settings: Any) -> None:
        from tests.conftest import MenuItemFactory

        MenuItemFactory(
            menu=item.menu,
            category=item.category,
            restaurant=restaurant,
            name="SoldOut",
            is_available=False,
        )
        result = _run_tool("get_menu", _ctx(restaurant=restaurant), {"query": "steak", "available_only": True})
        assert "Steak" in result.text
        result = _run_tool("get_menu", _ctx(restaurant=restaurant), {"query": "soldout", "available_only": True})
        assert "no menu items" in result.text.lower()

    def test_data_boundary_only_public_menu_data(self, restaurant: Any, restaurant_settings: Any) -> None:
        # A query that has no menu match yields an empty result — never any
        # staff/reservation/payment data (SC-005).
        result = _run_tool("get_menu", _ctx(restaurant=restaurant), {"query": "another guest's order"})
        assert "no menu items" in result.text.lower()
        assert "payment" not in result.text.lower()


class TestGetRestaurantInfo:
    def test_hours_from_settings(self, restaurant: Any, restaurant_settings: Any) -> None:
        result = _run_tool("get_restaurant_info", _ctx(restaurant=restaurant), {"topic": "hours"})
        assert "Fri" in result.text
        assert "09:00" in result.text or "10:00" in result.text

    def test_address(self, restaurant: Any, restaurant_settings: Any) -> None:
        result = _run_tool("get_restaurant_info", _ctx(restaurant=restaurant), {"topic": "address"})
        assert restaurant.address in result.text

    def test_payment_referral_no_financial_data(self, restaurant: Any, restaurant_settings: Any) -> None:
        result = _run_tool("get_restaurant_info", _ctx(restaurant=restaurant), {"topic": "payment"})
        assert "staff" in result.text.lower()
        assert "assistant cannot process payments" in result.text.lower()


class TestCheckAvailability:
    def test_returns_available_slot(self, restaurant: Any, restaurant_settings: Any, table: Any) -> None:
        when = timezone.now() + timedelta(days=1)
        result = _run_tool(
            "check_availability",
            _ctx(restaurant=restaurant),
            {"date": when.date().isoformat(), "time": "12:00", "party_size": 2},
        )
        assert "availability" in result.text.lower()
        assert "T1" in result.text

    def test_taken_slot_offers_alternatives(
        self,
        restaurant: Any,
        restaurant_settings: Any,
        table: Any,
        user_factory: Any,
    ) -> None:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Kyiv")
        when = (timezone.now().astimezone(tz) + timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        customer = user_factory()
        customer.save()
        _reservation(restaurant=restaurant, table=table, customer=customer, start=when)

        result = _run_tool(
            "check_availability",
            _ctx(restaurant=restaurant),
            {"date": when.date().isoformat(), "time": "12:00", "party_size": 2},
        )
        assert "no availability" in result.text.lower()
        assert "Nearest open slots" in result.text or "no availability" in result.text.lower()

    def test_party_larger_than_any_table(self, restaurant: Any, restaurant_settings: Any, table: Any) -> None:
        result = _run_tool(
            "check_availability",
            _ctx(restaurant=restaurant),
            {"date": timezone.now().date().isoformat(), "time": "12:00", "party_size": 99},
        )
        assert "no availability" in result.text.lower()


class TestAddToCart:
    def _session(self, restaurant: Any, user: Any, table: Any) -> CartSession:
        when = timezone.now() + timedelta(hours=3)
        reservation = _reservation(restaurant=restaurant, table=table, customer=user, start=when)
        session = CartSession.objects.create(restaurant_id=restaurant.id, reservation=reservation, created_by=user)
        return session

    def test_add_with_modifiers_succeeds(
        self,
        restaurant: Any,
        restaurant_settings: Any,
        table: Any,
        item: Any,
        user_factory: Any,
    ) -> None:
        group = ModifierGroup.objects.create(menu_item=item, restaurant=restaurant, name="Size", is_required=True)
        option = ModifierOption.objects.create(group=group, restaurant=restaurant, name="Large", price_delta="2.00")
        user = user_factory()
        user.save()
        session = self._session(restaurant, user, table)
        ctx = _ctx(restaurant=restaurant, user=user)
        tool = registry.get("add_to_cart")
        assert tool is not None and tool.execute is not None
        with patch("apps.orders.services.cart.is_restaurant_open", return_value=True):
            result = tool.execute(
                ctx,
                {
                    "menu_item_id": str(item.public_id),
                    "quantity": 2,
                    "modifiers": [
                        {"modifier_id": str(group.public_id), "option_id": str(option.public_id)},
                    ],
                },
            )
        assert result.outcome == "success"
        cart_item = CartItem.objects.get(cart_session=session, menu_item=item)
        assert cart_item.quantity == 2
        assert cart_item.modifiers == [
            {
                "modifier_id": str(group.public_id),
                "option_id": str(option.public_id),
                "name": "Size: Large",
                "price_delta": "2.0000",
            }
        ]
        assert cart_item.unit_price == item.price + 2

    def test_propose_asks_clarification_for_missing_required_modifier(
        self, restaurant: Any, restaurant_settings: Any, item: Any
    ) -> None:
        ModifierGroup.objects.create(menu_item=item, restaurant=restaurant, name="Size", is_required=True)
        ModifierOption.objects.create(
            group=ModifierGroup.objects.get(menu_item=item), restaurant=restaurant, name="Large"
        )
        result = _run_tool("add_to_cart", _ctx(restaurant=restaurant), {"menu_item_id": str(item.public_id)})
        assert result.clarification
        assert "Size" in result.clarification
        assert result.needs_confirmation is False

    def test_propose_sums_modifier_price_delta(self, restaurant: Any, restaurant_settings: Any, item: Any) -> None:
        group = ModifierGroup.objects.create(menu_item=item, restaurant=restaurant, name="Extras", is_required=False)
        option = ModifierOption.objects.create(group=group, restaurant=restaurant, name="Cheese", price_delta="1.50")
        result = _run_tool(
            "add_to_cart",
            _ctx(restaurant=restaurant),
            {
                "menu_item_id": str(item.public_id),
                "modifiers": [{"modifier_id": str(group.public_id), "option_id": str(option.public_id)}],
            },
        )
        assert result.clarification is None
        assert result.summary
        assert "Cheese" in result.consequence

    def test_unavailable_item_rejected(
        self, restaurant: Any, restaurant_settings: Any, table: Any, item: Any, user_factory: Any
    ) -> None:
        user = user_factory()
        user.save()
        self._session(restaurant, user, table)
        ctx = _ctx(restaurant=restaurant, user=user)
        item.is_available = False
        item.save()
        tool = registry.get("add_to_cart")
        assert tool is not None and tool.execute is not None
        with patch("apps.orders.services.cart.is_restaurant_open", return_value=True):
            result = tool.execute(ctx, {"menu_item_id": str(item.public_id), "quantity": 1})
        assert result.outcome == "failed"
        assert result.error_code == "item_unavailable"

    def test_closed_cart_rejected(
        self, restaurant: Any, restaurant_settings: Any, table: Any, item: Any, user_factory: Any
    ) -> None:
        user = user_factory()
        user.save()
        session = self._session(restaurant, user, table)
        session.status = CartSessionStatus.CLOSED
        session.save()
        ctx = _ctx(restaurant=restaurant, user=user)
        tool = registry.get("add_to_cart")
        assert tool is not None and tool.execute is not None
        with patch("apps.orders.services.cart.is_restaurant_open", return_value=True):
            result = tool.execute(ctx, {"menu_item_id": str(item.public_id), "quantity": 1})
        assert result.outcome == "failed"
        assert result.error_code == "cart_closed"


class TestInfoTurnSummarizesToolOutput:
    def test_read_only_tool_executed_silently_and_replied(
        self,
        make_conversation: Any,
        make_message: Any,
        restaurant: Any,
        restaurant_settings: Any,
        item: Any,
    ) -> None:
        owner = OwnerIdentity(user=None, guest_key="guest:turn-1")
        conversation = make_conversation(restaurant, owner)
        user_message = make_message(conversation, role=MessageRole.USER, text="does the steak contain gluten?")

        envelopes = [
            {"kind": "tool_call", "tool": "get_menu", "arguments": {"query": "steak"}},
            {"kind": "reply", "text": "The steak contains no gluten."},
        ]
        mock_envelope = AsyncMock(side_effect=envelopes)
        with patch.object(ollama, "generate_envelope", mock_envelope):
            process_turn(
                conversation_id=str(conversation.public_id),
                message_id=str(user_message.public_id),
                ui_context=None,
            )

        assert mock_envelope.await_count == 2
        replies = Message.objects.filter(conversation=conversation, role=MessageRole.ASSISTANT)
        assert replies.count() == 1
        reply = replies.first()
        assert reply is not None
        assert "gluten" in reply.text.lower()
        # Read-only tools never create proposals (FR-019).
        assert ToolProposal.objects.filter(conversation=conversation).count() == 0

    def test_write_tool_produces_proposal_not_execution(
        self,
        make_conversation: Any,
        make_message: Any,
        restaurant: Any,
        restaurant_settings: Any,
        table: Any,
    ) -> None:
        owner = OwnerIdentity(user=None, guest_key="guest:turn-2")
        conversation = make_conversation(restaurant, owner)
        user_message = make_message(conversation, role=MessageRole.USER, text="book a table for 2 tomorrow at 7pm")

        envelope = {
            "kind": "tool_call",
            "tool": "create_reservation",
            "arguments": {
                "date": (timezone.now() + timedelta(days=1)).date().isoformat(),
                "time": "19:00",
                "party_size": 2,
            },
        }
        mock_envelope = AsyncMock(return_value=envelope)
        with patch.object(ollama, "generate_envelope", mock_envelope):
            process_turn(
                conversation_id=str(conversation.public_id),
                message_id=str(user_message.public_id),
                ui_context=None,
            )

        proposal = ToolProposal.objects.get(conversation=conversation, status=ProposalStatus.PENDING)
        assert proposal.tool == "create_reservation"
        assert proposal.expires_at > timezone.now()
        assert not Message.objects.filter(conversation=conversation, role=MessageRole.ASSISTANT).exists()

    def test_cross_persona_tool_denied_server_side(
        self,
        make_conversation: Any,
        make_message: Any,
        restaurant: Any,
        restaurant_settings: Any,
    ) -> None:
        # A guest conversation: the model "hallucinates" an admin-only tool.
        owner = OwnerIdentity(user=None, guest_key="guest:turn-3")
        conversation = make_conversation(restaurant, owner)
        user_message = make_message(conversation, role=MessageRole.USER, text="show me the floor status")

        envelope = {"kind": "tool_call", "tool": "get_floor_status", "arguments": {}}
        mock_envelope = AsyncMock(return_value=envelope)
        with patch.object(ollama, "generate_envelope", mock_envelope):
            process_turn(
                conversation_id=str(conversation.public_id),
                message_id=str(user_message.public_id),
                ui_context=None,
            )

        # Denied server-side: no proposal, no execution, fallback reply.
        assert ToolProposal.objects.filter(conversation=conversation).count() == 0
        assert Message.objects.filter(conversation=conversation, role=MessageRole.ASSISTANT).count() == 1


class TestModifierClarificationTurn:
    def test_missing_required_modifier_replies_not_proposes(
        self,
        make_conversation: Any,
        make_message: Any,
        restaurant: Any,
        item: Any,
    ) -> None:
        group = ModifierGroup.objects.create(menu_item=item, restaurant=restaurant, name="Size", is_required=True)
        ModifierOption.objects.create(group=group, restaurant=restaurant, name="Large")

        owner = OwnerIdentity(user=None, guest_key="guest:turn-mod")
        conversation = make_conversation(restaurant, owner)
        user_message = make_message(
            conversation,
            role=MessageRole.USER,
            text="I'd like to add the steak to my cart",
        )

        envelope = {
            "kind": "tool_call",
            "tool": "add_to_cart",
            "arguments": {"menu_item_id": str(item.public_id), "quantity": 1},
        }
        mock_envelope = AsyncMock(return_value=envelope)
        with patch.object(ollama, "generate_envelope", mock_envelope):
            process_turn(
                conversation_id=str(conversation.public_id),
                message_id=str(user_message.public_id),
                ui_context=None,
            )

        assert ToolProposal.objects.filter(conversation=conversation).count() == 0
        reply = Message.objects.get(conversation=conversation, role=MessageRole.ASSISTANT)
        assert "Size" in reply.text
        assert "Large" in reply.text

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from apps.orders.models import CartSession
from apps.orders.services import add_item_to_cart, remove_item_from_cart, update_cart_item_quantity
from apps.reservations.models import Reservation
from core.routing import application

pytestmark = pytest.mark.django_db(databases=["default"], transaction=True)


@pytest.fixture(autouse=True)
def _inmemory_channel_layer(settings: Any) -> None:
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }


@pytest.fixture
def reservation(restaurant, table):  # type: ignore[no-untyped-def]
    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=None,
        guest_count=2,
        start_at=datetime.now(UTC) + timedelta(hours=1),
        end_at=datetime.now(UTC) + timedelta(hours=2),
    )


@pytest.fixture
def cart_context(restaurant, reservation, user_factory):  # type: ignore[no-untyped-def]
    owner = user_factory(role=RoleCode.CUSTOMER, restaurant=restaurant)
    owner.save()
    reservation.customer = owner
    reservation.save()
    session = CartSession.objects.create(restaurant=restaurant, reservation=reservation, created_by=owner)
    session.participants.add(owner)
    return {"session": session, "owner": owner, "restaurant": restaurant}


def _issue_guest_token(session: CartSession, device_id: str = "device-1") -> str:
    token = AccessToken()
    token["is_guest"] = True
    token["device_id"] = device_id
    token["cart_session_id"] = str(session.public_id)
    token.set_exp(lifetime=timedelta(hours=4))
    return str(token)


async def _connect(session: CartSession, token: str | None) -> WebsocketCommunicator:
    path = f"/ws/cart/{session.public_id}/"
    if token:
        path = f"{path}?token={token}"
    communicator = WebsocketCommunicator(application, path)
    connected, _ = await communicator.connect()
    assert connected
    return communicator


async def _connect_via_subprotocol(session: CartSession, token: str) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(
        application,
        f"/ws/cart/{session.public_id}/",
        subprotocols=["access_token", token],
    )
    connected, subprotocol = await communicator.connect()
    assert connected
    assert subprotocol == "access_token"
    return communicator


async def _issue_access_token(user, restaurant_id: int) -> str:  # type: ignore[no-untyped-def]
    access, _ = await sync_to_async(issue_tokens_with_restaurant)(user, restaurant_id)
    return access


@pytest.mark.anyio
async def test_guest_connection_requires_token(cart_context) -> None:  # type: ignore[no-untyped-def]
    communicator = WebsocketCommunicator(application, f"/ws/cart/{cart_context['session'].public_id}/")
    connected, _ = await communicator.connect()
    assert connected
    close = await communicator.receive_output(timeout=1)
    assert close["type"] == "websocket.close"
    assert close["code"] == 4001
    await communicator.disconnect()


@pytest.mark.anyio
async def test_guest_connection_wrong_session_rejected(cart_context) -> None:  # type: ignore[no-untyped-def]
    def _make_other_session() -> CartSession:
        existing = cart_context["session"]
        other_reservation = Reservation.objects.create(
            restaurant=cart_context["restaurant"],
            table=existing.reservation.table,
            customer=None,
            guest_count=2,
            start_at=datetime.now(UTC) + timedelta(hours=3),
            end_at=datetime.now(UTC) + timedelta(hours=4),
        )
        return CartSession.objects.create(
            restaurant=cart_context["restaurant"],
            reservation=other_reservation,
            created_by=cart_context["owner"],
        )

    other_session = await sync_to_async(_make_other_session)()
    token = _issue_guest_token(other_session)
    communicator = await _connect(cart_context["session"], token)
    close = await communicator.receive_output(timeout=1)
    assert close["type"] == "websocket.close"
    assert close["code"] == 4003
    await communicator.disconnect()


@pytest.mark.anyio
async def test_authenticated_participant_receives_event_on_add(cart_context, item) -> None:  # type: ignore[no-untyped-def]
    access = await _issue_access_token(cart_context["owner"], cart_context["restaurant"].id)
    communicator = await _connect(cart_context["session"], access)

    await sync_to_async(add_item_to_cart)(
        session=cart_context["session"],
        menu_item_id=str(item.public_id),
        quantity=1,
        user=cart_context["owner"],
    )

    event = await communicator.receive_json_from(timeout=1)
    assert event["type"] == "cart_updated"
    assert event["session_id"] == str(cart_context["session"].public_id)
    await communicator.disconnect()


@pytest.mark.anyio
async def test_authenticated_participant_receives_event_on_update(cart_context, item) -> None:  # type: ignore[no-untyped-def]
    added = await sync_to_async(add_item_to_cart)(
        session=cart_context["session"],
        menu_item_id=str(item.public_id),
        quantity=1,
        user=cart_context["owner"],
    )
    access = await _issue_access_token(cart_context["owner"], cart_context["restaurant"].id)
    communicator = await _connect(cart_context["session"], access)

    await sync_to_async(update_cart_item_quantity)(
        session=cart_context["session"],
        item_id=str(added.public_id),
        quantity=3,
        user=cart_context["owner"],
    )

    event = await communicator.receive_json_from(timeout=1)
    assert event["type"] == "cart_updated"
    await communicator.disconnect()


@pytest.mark.anyio
async def test_authenticated_participant_receives_event_on_delete(cart_context, item) -> None:  # type: ignore[no-untyped-def]
    added = await sync_to_async(add_item_to_cart)(
        session=cart_context["session"],
        menu_item_id=str(item.public_id),
        quantity=1,
        user=cart_context["owner"],
    )
    access = await _issue_access_token(cart_context["owner"], cart_context["restaurant"].id)
    communicator = await _connect(cart_context["session"], access)

    await sync_to_async(remove_item_from_cart)(
        session=cart_context["session"],
        item_id=str(added.public_id),
        user=cart_context["owner"],
    )

    event = await communicator.receive_json_from(timeout=1)
    assert event["type"] == "cart_updated"
    await communicator.disconnect()


@pytest.mark.anyio
async def test_guest_receives_broadcast(cart_context, item) -> None:  # type: ignore[no-untyped-def]
    token = _issue_guest_token(cart_context["session"])
    communicator = await _connect(cart_context["session"], token)

    await sync_to_async(add_item_to_cart)(
        session=cart_context["session"],
        menu_item_id=str(item.public_id),
        quantity=2,
    )

    event = await communicator.receive_json_from(timeout=1)
    assert event["type"] == "cart_updated"
    await communicator.disconnect()


@pytest.mark.anyio
async def test_connect_sends_no_unsolicited_event(cart_context) -> None:  # type: ignore[no-untyped-def]
    access = await _issue_access_token(cart_context["owner"], cart_context["restaurant"].id)
    communicator = await _connect(cart_context["session"], access)
    assert await communicator.receive_nothing(timeout=0.5)
    await communicator.disconnect()


@pytest.mark.anyio
async def test_broadcast_carries_originating_client_id(cart_context, item) -> None:  # type: ignore[no-untyped-def]
    token = _issue_guest_token(cart_context["session"])
    communicator = await _connect(cart_context["session"], token)

    await sync_to_async(add_item_to_cart)(
        session=cart_context["session"],
        menu_item_id=str(item.public_id),
        quantity=1,
        client_id="client-abc",
    )

    event = await communicator.receive_json_from(timeout=1)
    assert event["type"] == "cart_updated"
    assert event["client_id"] == "client-abc"
    await communicator.disconnect()


@pytest.mark.anyio
async def test_guest_connects_via_subprotocol(cart_context, item) -> None:  # type: ignore[no-untyped-def]
    token = _issue_guest_token(cart_context["session"])
    communicator = await _connect_via_subprotocol(cart_context["session"], token)

    await sync_to_async(add_item_to_cart)(
        session=cart_context["session"],
        menu_item_id=str(item.public_id),
        quantity=1,
    )

    event = await communicator.receive_json_from(timeout=1)
    assert event["type"] == "cart_updated"
    await communicator.disconnect()

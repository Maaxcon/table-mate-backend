from __future__ import annotations

from typing import Any

import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator

from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens
from common.hall_events import emit_hall_table_status_changed
from core.routing import application
from tests.conftest import UserFactory

pytestmark_rt = pytest.mark.django_db(databases=["default"], transaction=True)


@pytest.fixture(autouse=True)
def _inmemory_channel_layer(settings: Any) -> None:
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }


async def _customer_token() -> tuple[Any, str]:
    user = await sync_to_async(UserFactory.build)(role=RoleCode.CUSTOMER)
    await sync_to_async(user.save)()
    access, _ = await sync_to_async(issue_tokens)(user)
    return user, access


@pytestmark_rt
async def test_customer_connects_to_floor_with_restaurant_query(restaurant: Any) -> None:
    _, access = await _customer_token()
    communicator = WebsocketCommunicator(
        application, f"/ws/floor/?token={access}&restaurant={restaurant.public_id}"
    )
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()


@pytestmark_rt
async def test_customer_rejected_without_restaurant_query(restaurant: Any) -> None:
    _, access = await _customer_token()
    communicator = WebsocketCommunicator(application, f"/ws/floor/?token={access}")
    await communicator.connect()
    output = await communicator.receive_output(timeout=5)
    assert output["type"] == "websocket.close"
    assert output["code"] == 4001
    await communicator.disconnect()


@pytestmark_rt
async def test_customer_receives_filtered_floor_broadcast(restaurant: Any, table: Any) -> None:
    user, access = await _customer_token()
    communicator = WebsocketCommunicator(
        application, f"/ws/floor/?token={access}&restaurant={restaurant.public_id}"
    )
    connected, _ = await communicator.connect()
    assert connected

    await sync_to_async(emit_hall_table_status_changed)(
        restaurant.id,
        table_id=str(table.public_id),
        previous_status="free",
        current_status="occupied",
        session_id="test-session",
        actor=user,
    )

    event = await communicator.receive_json_from(timeout=5)
    assert event["event_name"] == "HALL_TABLE_STATUS_CHANGED"
    assert event["table_id"] == str(table.public_id)
    assert event["current_status"] == "occupied"
    # The floor stream strips staff-only fields.
    assert "actor_id" not in event
    assert "session_id" not in event

    await communicator.disconnect()

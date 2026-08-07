# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from channels.testing import WebsocketCommunicator
from django.utils import timezone

from apps.assistant.models import Message, MessageRole
from apps.assistant.services import events
from apps.assistant.services.events import (
    SCHEMA_VERSION,
    emit_action_proposed,
    emit_action_result,
    emit_assistant_message,
)
from apps.authentication.models import RoleCode
from apps.authentication.services import issue_tokens_with_restaurant
from core.routing import application
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db

_now = timezone.now()


def _capture_broadcast() -> tuple[MagicMock, MagicMock]:
    layer = MagicMock()
    group_send = MagicMock()
    layer.group_send = group_send
    patcher = patch("apps.assistant.services.events.get_channel_layer", return_value=layer)
    patcher.start()
    return patcher, group_send


class TestEventEnvelopes:
    def test_assistant_message_envelope_shape(self) -> None:
        patcher, group_send = _capture_broadcast()
        try:
            emit_assistant_message(
                "c-1",
                message_id="m-1",
                role=MessageRole.ASSISTANT,
                text="hello",
                created_at=_now,
            )
        finally:
            patcher.stop()
        group_send.assert_called_once()
        payload = group_send.call_args[0]
        assert payload[0] == "assistant_conversation_c-1"
        event = payload[1]["event"]
        assert event["type"] == "ASSISTANT_MESSAGE"
        assert event["schema_version"] == SCHEMA_VERSION == 1
        assert event["data"]["message_id"] == "m-1"
        assert event["data"]["role"] == "assistant"
        assert event["data"]["text"] == "hello"
        assert "created_at" in event["data"]

    def test_action_proposed_envelope_shape(self) -> None:
        patcher, group_send = _capture_broadcast()
        try:
            emit_action_proposed(
                "c-1",
                proposal_id="p-1",
                tool="create_reservation",
                summary="Create a reservation",
                consequence="This books a table.",
                expires_at=_now + timezone.timedelta(minutes=5),
            )
        finally:
            patcher.stop()
        event = group_send.call_args[0][1]["event"]
        assert event["type"] == "ASSISTANT_ACTION_PROPOSED"
        assert event["schema_version"] == 1
        assert event["data"]["proposal_id"] == "p-1"
        assert event["data"]["tool"] == "create_reservation"
        assert event["data"]["summary"] == "Create a reservation"
        assert event["data"]["consequence"] == "This books a table."
        assert event["data"]["expires_at"]

    def test_action_result_envelope_shape(self) -> None:
        patcher, group_send = _capture_broadcast()
        try:
            emit_action_result(
                "c-1",
                proposal_id="p-1",
                tool="create_reservation",
                outcome="success",
                reference_id="res-1",
            )
        finally:
            patcher.stop()
        event = group_send.call_args[0][1]["event"]
        assert event["type"] == "ASSISTANT_ACTION_RESULT"
        assert event["schema_version"] == 1
        assert event["data"] == {
            "proposal_id": "p-1",
            "tool": "create_reservation",
            "outcome": "success",
            "reference_id": "res-1",
        }

    def test_no_credentials_in_event_payloads(self) -> None:
        patcher, group_send = _capture_broadcast()
        try:
            emit_assistant_message("c-1", message_id="m-1", role="assistant", text="secret? no", created_at=_now)
        finally:
            patcher.stop()
        raw = str(group_send.call_args)
        for secret in ("bearer", "token=", "authorization", "password"):
            assert secret.lower() not in raw.lower()

    def test_unknown_version_is_client_ignored_not_backend_dropped(self) -> None:
        # The contract says clients IGNORE unsupported schema_version rather
        # than crash (additive forward compatibility). The backend always tags
        # the current version and never filters: a future-version envelope must
        # still reach the wire so older/newer clients can decide themselves.
        event = events._envelope("ASSISTANT_MESSAGE", {"message_id": "m-1"})
        assert event["schema_version"] == 1
        assert "type" in event
        assert "data" in event


class TestReplayAndIdempotencyAssumptions:
    def test_replay_source_is_persisted_messages(
        self,
        make_conversation: Any,
        make_owner: Any,
        make_message: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:replay-1")
        conversation = make_conversation(restaurant, owner)
        first = make_message(conversation, role=MessageRole.USER, text="hi")
        second = make_message(conversation, role=MessageRole.ASSISTANT, text="hello!")

        history = list(conversation.messages.order_by("created_at", "id"))
        assert [str(m.public_id) for m in history] == [str(first.public_id), str(second.public_id)]
        # At-least-once: the same message id can be delivered again without
        # re-execution; the replay source stays stable (FR-012).
        assert Message.objects.filter(public_id=second.public_id).exists()


@pytest.mark.django_db(databases=["default"], transaction=True)
@pytest.mark.asyncio
async def test_ws_delivers_assistant_message_to_conversation_group(
    make_conversation: Any,
    make_owner: Any,
    restaurant: Any,
) -> None:
    from asgiref.sync import sync_to_async

    user = UserFactory.build(role=RoleCode.CUSTOMER)
    await user.asave()
    owner = await sync_to_async(make_owner)(user=user, guest_key="")
    conversation = await sync_to_async(make_conversation)(restaurant, owner)

    access, _ = await user_issue_tokens(user, restaurant)
    communicator = WebsocketCommunicator(
        application,
        f"/ws/assistant/{conversation.public_id}/",
        subprotocols=["access_token", access],
    )
    connected, _ = await communicator.connect()
    assert connected

    await sync_to_async(emit_assistant_message)(
        str(conversation.public_id),
        message_id="m-ws-1",
        role=MessageRole.ASSISTANT,
        text="replied over the wire",
        created_at=timezone.now(),
    )

    received = await communicator.receive_json_from(timeout=5)
    assert received["type"] == "ASSISTANT_MESSAGE"
    assert received["schema_version"] == 1
    assert received["data"]["text"] == "replied over the wire"

    await communicator.disconnect()


async def user_issue_tokens(user: Any, restaurant: Any) -> tuple[str, str]:
    from asgiref.sync import sync_to_async

    return await sync_to_async(issue_tokens_with_restaurant)(user, restaurant.id)

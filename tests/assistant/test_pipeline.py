# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from django.test.utils import override_settings

from apps.assistant.models import Message, MessageRole
from apps.assistant.services.pipeline import ingest_message
from apps.assistant.services.rate_limit import RateLimitExceededError

pytestmark = pytest.mark.django_db


class TestIngestMessage:
    def test_persists_message_and_enqueues(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:pipeline-1")
        conversation = make_conversation(restaurant, owner)

        with patch("apps.assistant.tasks.assistant_process_turn") as task:
            message = ingest_message(
                restaurant_id=restaurant.id,
                conversation=conversation,
                owner=owner,
                text="  does the pasta have gluten?  ",
                ui_context={"active_view": "menu"},
            )

        assert message.role == MessageRole.USER
        assert message.text == "  does the pasta have gluten?  "
        task.delay.assert_called_once()
        assert task.delay.call_args[0][0] == str(conversation.public_id)
        assert task.delay.call_args[0][1] == str(message.public_id)

    @override_settings(ASSISTANT_HOURLY_CAP=1, ASSISTANT_DAILY_CAP=100)
    def test_hourly_cap_raises_without_persisting_or_enqueueing(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:capped-1")
        conversation = make_conversation(restaurant, owner)

        with patch("apps.assistant.tasks.assistant_process_turn") as task:
            ingest_message(
                restaurant_id=restaurant.id,
                conversation=conversation,
                owner=owner,
                text="first",
                ui_context=None,
            )
            with pytest.raises(RateLimitExceededError):
                ingest_message(
                    restaurant_id=restaurant.id,
                    conversation=conversation,
                    owner=owner,
                    text="second",
                    ui_context=None,
                )

        task.delay.assert_called_once()
        assert Message.objects.filter(conversation=conversation).count() == 1

    @override_settings(ASSISTANT_HOURLY_CAP=100, ASSISTANT_DAILY_CAP=1)
    def test_daily_cap_raises(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:daily-capped")
        conversation = make_conversation(restaurant, owner)

        with patch("apps.assistant.tasks.assistant_process_turn"):
            ingest_message(
                restaurant_id=restaurant.id, conversation=conversation, owner=owner, text="a", ui_context=None
            )
            with pytest.raises(RateLimitExceededError):
                ingest_message(
                    restaurant_id=restaurant.id,
                    conversation=conversation,
                    owner=owner,
                    text="b",
                    ui_context=None,
                )

    def test_rate_limit_is_per_owner(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
    ) -> None:
        owner_a = make_owner(user=None, guest_key="guest:owner-a")
        owner_b = make_owner(user=None, guest_key="guest:owner-b")
        conversation_a = make_conversation(restaurant, owner_a)
        conversation_b = make_conversation(restaurant, owner_b)

        with patch("apps.assistant.tasks.assistant_process_turn") as task:
            ingest_message(
                restaurant_id=restaurant.id, conversation=conversation_a, owner=owner_a, text="a1", ui_context=None
            )
            ingest_message(
                restaurant_id=restaurant.id,
                conversation=conversation_b,
                owner=owner_b,
                text="b1",
                ui_context=None,
            )

        assert task.delay.call_count == 2


class TestProcessTurnMalformedInput:
    def test_empty_text_is_rejected_by_serializer(self, api: Any, restaurant: Any) -> None:
        api = api(role="customer", restaurant_id=restaurant.id)
        response = api.client.post(
            "/api/assistant/conversations/",
            {"language": "en"},
            format="json",
        )
        assert response.status_code == 201
        conversation_id = response.data["conversation_id"]

        response = api.client.post(
            f"/api/assistant/conversations/{conversation_id}/messages/",
            {"text": "   "},
            format="json",
        )
        assert response.status_code == 400

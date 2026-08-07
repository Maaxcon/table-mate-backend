# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.assistant.models import MessageRole
from apps.authentication.models import RoleCode

pytestmark = pytest.mark.django_db


def _create_conversation(client: Any, *, language: str = "en") -> dict[str, Any]:
    response = client.post("/api/assistant/conversations/", {"language": language}, format="json")
    assert response.status_code == 201, response.data
    return response.data


class TestConversationAPI:
    def test_create_conversation(self, api: Any, restaurant: Any) -> None:
        client = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id).client
        data = _create_conversation(client, language="en")
        assert data["conversation_id"]
        assert data["status"] == "active"
        assert data["language"] == "en"
        assert "created_at" in data

    def test_resume_existing_conversation(self, api: Any, restaurant: Any) -> None:
        client = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id).client
        first = _create_conversation(client)
        second = _create_conversation(client)
        assert first["conversation_id"] == second["conversation_id"]

    def test_unauth_request_rejected(self, restaurant: Any) -> None:
        response = APIClient().post("/api/assistant/conversations/", {"language": "en"}, format="json")
        assert response.status_code in (401, 403)

    def test_detail_returns_pending_proposal_and_recent_messages(
        self,
        api: Any,
        restaurant: Any,
        make_message: Any,
    ) -> None:
        client, user = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id)
        data = _create_conversation(client)
        conversation_id = data["conversation_id"]

        from apps.assistant.models import Conversation

        conversation = Conversation.objects.get(public_id=conversation_id)
        make_message(conversation, role=MessageRole.USER, text="hello")

        response = client.get(f"/api/assistant/conversations/{conversation_id}/")
        assert response.status_code == 200
        payload = response.data
        assert payload["conversation_id"] == conversation_id
        assert payload["pending_proposal"] is None
        assert len(payload["recent_messages"]) == 1
        assert payload["recent_messages"][0]["role"] == "user"
        assert payload["recent_messages"][0]["text"] == "hello"

    def test_other_user_cannot_read_conversation(self, api: Any, restaurant: Any) -> None:
        owner = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id).client
        conversation_id = _create_conversation(owner)["conversation_id"]

        other = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id).client
        assert other.get(f"/api/assistant/conversations/{conversation_id}/").status_code == 404
        assert other.get(f"/api/assistant/conversations/{conversation_id}/messages/").status_code == 404

    def test_unknown_conversation_404(self, api: Any, restaurant: Any) -> None:
        client = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id).client
        assert client.get("/api/assistant/conversations/00000000-0000-0000-0000-000000000000/").status_code == 404


class TestMessagesAPI:
    def test_post_message_202_with_message_id(self, api: Any, restaurant: Any) -> None:
        client = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id).client
        conversation_id = _create_conversation(client)["conversation_id"]

        with patch("apps.assistant.tasks.assistant_process_turn") as task:
            response = client.post(
                f"/api/assistant/conversations/{conversation_id}/messages/",
                {"text": "does the risotto contain gluten?", "ui_context": {"active_view": "menu"}},
                format="json",
            )
        assert response.status_code == 202
        assert response.data["conversation_id"] == conversation_id
        assert response.data["message_id"]
        task.delay.assert_called_once()

    def test_post_empty_text_rejected(self, api: Any, restaurant: Any) -> None:
        client = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id).client
        conversation_id = _create_conversation(client)["conversation_id"]
        response = client.post(
            f"/api/assistant/conversations/{conversation_id}/messages/",
            {"text": "   "},
            format="json",
        )
        assert response.status_code == 400

    def test_post_invalid_ui_context_rejected(self, api: Any, restaurant: Any) -> None:
        client = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id).client
        conversation_id = _create_conversation(client)["conversation_id"]
        response = client.post(
            f"/api/assistant/conversations/{conversation_id}/messages/",
            {"text": "hi", "ui_context": "not-an-object"},
            format="json",
        )
        assert response.status_code == 400

    def test_history_replay_shape(self, api: Any, restaurant: Any, make_message: Any) -> None:
        client = api(role=RoleCode.CUSTOMER, restaurant_id=restaurant.id).client
        conversation_id = _create_conversation(client)["conversation_id"]

        from apps.assistant.models import Conversation

        conversation = Conversation.objects.get(public_id=conversation_id)
        make_message(conversation, role=MessageRole.USER, text="first")
        make_message(conversation, role=MessageRole.ASSISTANT, text="second")

        response = client.get(f"/api/assistant/conversations/{conversation_id}/messages/")
        assert response.status_code == 200
        assert "results" in response.data
        assert "next" in response.data
        assert [m["role"] for m in response.data["results"]] == ["user", "assistant"]
        assert [m["text"] for m in response.data["results"]] == ["first", "second"]
        for m in response.data["results"]:
            assert set(m) == {"message_id", "role", "text", "created_at"}

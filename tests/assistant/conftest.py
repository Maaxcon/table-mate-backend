# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.assistant.models import Conversation, Message, MessageRole, ProposalStatus, ToolProposal
from apps.assistant.services.conversations import get_or_create_conversation
from apps.assistant.services.identity import OwnerIdentity

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _inmemory_channel_layer(settings: Any) -> Iterator[None]:
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
    yield


@pytest.fixture
def make_owner() -> Callable[..., OwnerIdentity]:
    def _make_owner(user: Any | None = None, guest_key: str = "") -> OwnerIdentity:
        if user is not None:
            return OwnerIdentity(user=user, guest_key="")
        return OwnerIdentity(user=None, guest_key=guest_key or "guest:test-1")

    return _make_owner


@pytest.fixture
def make_conversation() -> Callable[..., Conversation]:
    def _make_conversation(restaurant: Any, owner: OwnerIdentity, language: str | None = None) -> Conversation:
        return get_or_create_conversation(restaurant_id=restaurant.id, owner=owner, language=language)

    return _make_conversation


@pytest.fixture
def make_proposal() -> Callable[..., ToolProposal]:
    def _make_proposal(
        conversation: Conversation,
        *,
        tool: str = "create_reservation",
        parameters: dict[str, Any] | None = None,
        status: str = ProposalStatus.PENDING,
        owner: OwnerIdentity | None = None,
        expires_in: timedelta | None = None,
    ) -> ToolProposal:
        owner = owner or OwnerIdentity(
            user=conversation.user if conversation.user_id else None,
            guest_key=conversation.guest_key or "",
        )
        expires_at = timezone.now() + (expires_in or timedelta(minutes=5))
        from django.contrib.auth import get_user_model

        user = owner.user
        if not isinstance(user, get_user_model()):
            user = None
        return ToolProposal.objects.create(
            conversation=conversation,
            user=user,
            guest_key=owner.guest_key if owner.user is None else "",
            tool=tool,
            parameters=parameters or {},
            summary=f"Execute {tool}",
            consequence="This performs the requested action.",
            status=status,
            expires_at=expires_at,
        )

    return _make_proposal


@pytest.fixture
def make_message() -> Callable[..., Message]:
    def _make_message(conversation: Conversation, *, role: str = MessageRole.USER, text: str = "hello") -> Message:
        return Message.objects.create(conversation=conversation, role=role, text=text)

    return _make_message


__all__ = [
    "_inmemory_channel_layer",
    "make_conversation",
    "make_message",
    "make_owner",
    "make_proposal",
]

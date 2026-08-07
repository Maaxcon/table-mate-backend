from typing import TYPE_CHECKING

from django.db.models import QuerySet

from .models import (
    Conversation,
    HandoffRequest,
    HandoffStatus,
    Message,
    ProposalStatus,
    ToolProposal,
)

if TYPE_CHECKING:
    from apps.authentication.models import User


def get_conversation(conversation_id: str, restaurant_id: int) -> Conversation | None:
    try:
        return Conversation.objects.filter(
            public_id=conversation_id,
            restaurant_id=restaurant_id,
        ).select_related("restaurant").first()
    except (ValueError, TypeError):
        return None


def get_owned_conversation(
    conversation_id: str,
    restaurant_id: int,
    user: "User | None",
    guest_key: str,
) -> Conversation | None:
    conversation = get_conversation(conversation_id, restaurant_id)
    if conversation is None:
        return None
    if user is not None and conversation.user_id == user.pk:
        return conversation
    if user is None and guest_key and conversation.guest_key == guest_key:
        return conversation
    return None


def get_messages(conversation: Conversation) -> QuerySet[Message]:
    return conversation.messages.order_by("created_at", "id")


def get_recent_messages(conversation: Conversation, limit: int = 40) -> list[Message]:
    return list(conversation.messages.order_by("-created_at", "-id")[:limit][::-1])


def get_pending_proposal(conversation: Conversation) -> ToolProposal | None:
    return (
        conversation.proposals.filter(
            status=ProposalStatus.PENDING,
        )
        .order_by("-created_at")
        .first()
    )


def get_proposal(proposal_id: str) -> ToolProposal | None:
    try:
        return (
            ToolProposal.objects.select_related("conversation__restaurant")
            .filter(public_id=proposal_id)
            .first()
        )
    except (ValueError, TypeError):
        return None


def get_owned_proposal(
    proposal_id: str,
    restaurant_id: int,
    user: "User | None",
    guest_key: str,
) -> ToolProposal | None:
    proposal = get_proposal(proposal_id)
    if proposal is None or proposal.conversation.restaurant_id != restaurant_id:
        return None
    if user is not None and proposal.conversation.user_id == user.pk:
        return proposal
    if user is None and guest_key and proposal.conversation.guest_key == guest_key:
        return proposal
    return None


def get_open_handoffs(restaurant_id: int) -> QuerySet[HandoffRequest]:
    return HandoffRequest.objects.filter(
        restaurant_id=restaurant_id,
        status=HandoffStatus.OPEN,
    ).order_by("created_at")


__all__ = [
    "get_conversation",
    "get_owned_conversation",
    "get_messages",
    "get_recent_messages",
    "get_pending_proposal",
    "get_proposal",
    "get_owned_proposal",
    "get_open_handoffs",
]

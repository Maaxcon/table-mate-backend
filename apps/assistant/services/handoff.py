from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from common.notification_events import _broadcast_staff_event

from ..models import Conversation, HandoffRequest, HandoffStatus
from ..selectors import get_recent_messages
from .events import staff_handoff_event


@transaction.atomic
def create_handoff(
    *,
    conversation: Conversation,
    reason: str,
) -> HandoffRequest:
    """Record a staff hand-off with conversation context and notify staff.

    FR-011: staff are notified through the existing ``staff_<restaurant_id>``
    stream + Redis notification store; no payment context is ever attached
    (FR-009).
    """
    context_summary = _build_context_summary(conversation)
    handoff = HandoffRequest.objects.create(
        conversation=conversation,
        restaurant_id=conversation.restaurant_id,
        status=HandoffStatus.OPEN,
        context_summary=context_summary,
        notes=reason or "",
        notified_at=timezone.now(),
    )

    event = staff_handoff_event(
        conversation.restaurant_id,
        handoff_id=str(handoff.public_id),
        conversation_id=str(conversation.public_id),
        context_summary=context_summary,
    )

    def _notify_staff() -> None:
        _broadcast_staff_event(conversation.restaurant_id, event)

    transaction.on_commit(_notify_staff)

    return handoff


def _build_context_summary(conversation: Conversation, limit: int = 8) -> str:
    messages = get_recent_messages(conversation, limit=limit)
    if not messages:
        return "Guest requested assistance; no conversation history yet."
    parts = [f"{m.role}: {m.text[:300]}" for m in messages]
    return "\n".join(parts)


__all__ = ["create_handoff"]

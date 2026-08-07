from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import Conversation, ToolCall
from .services.pipeline import process_turn
from .services.proposals import expire_stale_proposals

logger = logging.getLogger(__name__)


@shared_task(name="assistant.process_turn")
def assistant_process_turn(
    conversation_id: str,
    message_id: str,
    ui_context: dict[str, Any] | None = None,
) -> None:
    """Run one model turn for a persisted guest message (router -> model -> reply)."""
    try:
        process_turn(conversation_id=conversation_id, message_id=message_id, ui_context=ui_context)
    except Exception:
        logger.exception("assistant.process_turn failed for conversation %s", conversation_id)
        # Fail soft: a broken turn must not lose the guest message or wedge the queue.
        raise


@shared_task(name="assistant.followup")
def assistant_followup(conversation_id: str, proposal_id: str | None = None) -> None:
    """Post-reject/dismiss follow-up: acknowledge and re-offer against current state.

    The reply is deterministic (no extra model call) so a dismissed proposal
    always yields a stable, safe acknowledgment (Checkpoint Rule).
    """
    conversation = Conversation.objects.filter(public_id=conversation_id).first()
    if conversation is None:
        return
    from .models import Message, MessageRole
    from .services.events import emit_assistant_message

    reply = Message.objects.create(
        conversation=conversation,
        role=MessageRole.ASSISTANT,
        text="No problem — I won't do that. Would you like me to help with something else?",
    )
    emit_assistant_message(
        str(conversation.public_id),
        message_id=str(reply.public_id),
        role=reply.role,
        text=reply.text,
        created_at=reply.created_at,
    )


@shared_task(name="assistant.cleanup")
def assistant_cleanup() -> dict[str, int]:
    """Retention enforcement (FR-022/FR-024): conversations > 7 d, ToolCall > 30 d,
    and lazy expiry of stale pending proposals."""
    now = timezone.now()
    conversation_days = int(getattr(settings, "ASSISTANT_CONVERSATION_RETENTION_DAYS", 7))
    audit_days = int(getattr(settings, "ASSISTANT_AUDIT_RETENTION_DAYS", 30))

    conversations_deleted, _ = Conversation.objects.filter(
        created_at__lt=now - timezone.timedelta(days=conversation_days)
    ).delete()
    toolcalls_deleted, _ = ToolCall.objects.filter(
        executed_at__lt=now - timezone.timedelta(days=audit_days)
    ).delete()
    expired = expire_stale_proposals()

    logger.info(
        "assistant_cleanup: %s conversations, %s tool calls, %s stale proposals.",
        conversations_deleted,
        toolcalls_deleted,
        expired,
    )
    return {
        "conversations_deleted": conversations_deleted,
        "toolcalls_deleted": toolcalls_deleted,
        "stale_proposals_expired": expired,
    }


__all__ = ["assistant_cleanup", "assistant_followup", "assistant_process_turn"]

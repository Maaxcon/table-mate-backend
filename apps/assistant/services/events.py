from __future__ import annotations

import logging
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

EVENT_ASSISTANT_MESSAGE = "ASSISTANT_MESSAGE"
EVENT_ACTION_PROPOSED = "ASSISTANT_ACTION_PROPOSED"
EVENT_ACTION_RESULT = "ASSISTANT_ACTION_RESULT"


def assistant_group_name(conversation_id: object) -> str:
    return f"assistant_conversation_{conversation_id}"


def _envelope(event_type: str, data: dict[str, object]) -> dict[str, object]:
    return {"type": event_type, "schema_version": SCHEMA_VERSION, "data": data}


def _broadcast(conversation_id: str, event_type: str, data: dict[str, object]) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning("Channel layer unavailable; skipping assistant event %s", event_type)
        return
    try:
        async_to_sync(channel_layer.group_send)(
            assistant_group_name(conversation_id),
            {"type": "assistant.event", "event": _envelope(event_type, data)},
        )
    except Exception:
        logger.exception("Failed to broadcast assistant event %s", event_type)


def emit_assistant_message(
    conversation_id: str,
    *,
    message_id: str,
    role: str,
    text: str,
    created_at: object,
) -> None:
    _broadcast(
        conversation_id,
        EVENT_ASSISTANT_MESSAGE,
        {
            "message_id": message_id,
            "role": role,
            "text": text,
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        },
    )


def emit_action_proposed(
    conversation_id: str,
    *,
    proposal_id: str,
    tool: str,
    summary: str,
    consequence: str,
    expires_at: object,
) -> None:
    _broadcast(
        conversation_id,
        EVENT_ACTION_PROPOSED,
        {
            "proposal_id": proposal_id,
            "tool": tool,
            "summary": summary,
            "consequence": consequence,
            "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else expires_at,
        },
    )


def emit_action_result(
    conversation_id: str,
    *,
    proposal_id: str,
    tool: str,
    outcome: str,
    reference_id: str | None,
) -> None:
    _broadcast(
        conversation_id,
        EVENT_ACTION_RESULT,
        {
            "proposal_id": proposal_id,
            "tool": tool,
            "outcome": outcome,
            "reference_id": reference_id,
        },
    )


def new_event_id() -> str:
    return str(uuid.uuid4())


def staff_handoff_event(
    restaurant_id: int,
    *,
    handoff_id: str,
    conversation_id: str,
    context_summary: str,
) -> dict[str, object]:
    return {
        "type": "ASSISTANT_HANDOFF_REQUEST",
        "data": {
            "id": new_event_id(),
            "handoff_id": handoff_id,
            "conversation_id": conversation_id,
            "context_summary": context_summary[:500],
            "timestamp": timezone.now().isoformat(),
        },
    }


__all__ = [
    "EVENT_ACTION_PROPOSED",
    "EVENT_ACTION_RESULT",
    "EVENT_ASSISTANT_MESSAGE",
    "SCHEMA_VERSION",
    "assistant_group_name",
    "emit_action_proposed",
    "emit_action_result",
    "emit_assistant_message",
    "staff_handoff_event",
]

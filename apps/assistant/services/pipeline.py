from __future__ import annotations

import asyncio
import logging
from typing import Any

from rest_framework import serializers

from ..models import Conversation, Message, MessageRole
from ..selectors import get_recent_messages
from . import ollama, router
from .events import emit_action_proposed, emit_assistant_message
from .identity import OwnerIdentity
from .proposals import ClarificationRequiredError, create_proposal
from .rate_limit import check_rate_limit
from .registry import ToolContext, persona_for_role, registry
from .schemas import validate_tool_args

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20
FALLBACK_REPLY = (
    "I couldn't process that. Could you rephrase, or shall I hand you over to our staff?"
)


def ingest_message(
    *,
    restaurant_id: int,
    conversation: Conversation,
    owner: OwnerIdentity,
    text: str,
    ui_context: dict[str, Any] | None,
) -> Message:
    """Persist the guest message and enqueue the async model turn (202 path).

    Rate caps are enforced here, before any model work (FR-023).
    """
    check_rate_limit(owner.rate_limit_key, restaurant_id)
    message = Message.objects.create(
        conversation=conversation,
        role=MessageRole.USER,
        text=text,
    )
    from ..tasks import assistant_process_turn

    assistant_process_turn.delay(str(conversation.public_id), str(message.public_id), ui_context)
    return message


def _light_schema(serializer_cls: type[serializers.Serializer]) -> dict[str, Any]:
    """Derive a minimal JSON-schema-like shape from a DRF serializer (FR-018)."""
    serializer = serializer_cls()
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, field in serializer.fields.items():
        properties[name] = _field_to_schema(field)
        if getattr(field, "required", False):
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def _field_to_schema(field: serializers.Field) -> dict[str, Any]:
    if isinstance(field, serializers.BooleanField):
        return {"type": "boolean"}
    if isinstance(field, serializers.IntegerField):
        return {"type": "integer"}
    if isinstance(field, (serializers.DateField, serializers.TimeField, serializers.DateTimeField)):
        return {"type": "string"}
    if isinstance(field, serializers.ListField):
        return {"type": "array", "items": {"type": "object"}}
    if isinstance(field, serializers.ChoiceField):
        choices = getattr(field, "choices", None)
        if choices:
            return {"type": "string", "enum": list(choices)}
        return {"type": "string"}
    return {"type": "string"}


def _tool_specs(tool_names: list[str]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for name in tool_names:
        tool = registry.get(name)
        if tool is None:
            continue
        specs.append(
            {
                "name": tool.name,
                "description": tool.description,
                "schema": _light_schema(tool.schema),
            }
        )
    return specs


def process_turn(*, conversation_id: str, message_id: str, ui_context: dict[str, Any] | None = None) -> None:
    """Synchronous orchestration for the worker: router -> model -> persist/broadcast.

    Runs the async Ollama client via ``asyncio.run`` inside the Celery task.
    """
    conversation = (
        Conversation.objects.select_related("user", "restaurant")
        .filter(public_id=conversation_id)
        .first()
    )
    if conversation is None:
        return
    message = conversation.messages.filter(public_id=message_id).first()
    if message is None:
        return

    persona = persona_for_role(conversation.user.role if conversation.user_id else "customer")
    intent = router.categorize(message.text)
    offered = registry.tools_for_intent(intent, persona)
    system_prompt = ollama.build_system_prompt(
        persona=persona,
        intent=intent,
        tools=_tool_specs(offered),
        ui_context=ui_context,
        language=conversation.language,
    )

    history = _history_before(conversation, message_id)
    messages = ollama.build_chat_messages(
        system_prompt=system_prompt,
        history=history,
        latest_user_text=message.text,
    )

    try:
        envelope = asyncio.run(
            ollama.generate_envelope(
                system_prompt=system_prompt,
                messages=messages,
                model=ollama.default_model(),
                url=ollama.default_url(),
            )
        )
    except ollama.OllamaUnavailableError as exc:
        logger.warning("Ollama unreachable for conversation %s: %s", conversation_id, exc)
        _persist_and_broadcast_reply(conversation, FALLBACK_REPLY)
        return
    except ollama.MalformedOutputError as exc:
        logger.warning("Malformed model output for conversation %s: %s", conversation_id, exc)
        _persist_and_broadcast_reply(conversation, FALLBACK_REPLY)
        return

    if envelope["kind"] == "reply":
        _persist_and_broadcast_reply(conversation, str(envelope["text"]))
        return

    tool = str(envelope["tool"])
    if not _tool_allowed_for_turn(tool, offered, persona):
        logger.warning("Tool %s not allowed for persona %s in intent %s", tool, persona, intent)
        _persist_and_broadcast_reply(conversation, FALLBACK_REPLY)
        return

    arguments = dict(envelope.get("arguments") or {})
    tool_spec = registry.get(tool)
    if tool_spec is None:
        _persist_and_broadcast_reply(conversation, FALLBACK_REPLY)
        return

    ctx = ToolContext(
        restaurant_id=conversation.restaurant_id,
        owner=OwnerIdentity(
            user=conversation.user if conversation.user_id else None,
            guest_key=conversation.guest_key or "",
        ),
        user=conversation.user if conversation.user_id else None,
        guest_key=conversation.guest_key or "",
        conversation_id=str(conversation.public_id),
        language=conversation.language,
    )

    if tool_spec.needs_confirmation:
        try:
            validated = validate_tool_args(tool, arguments)
        except serializers.ValidationError:
            logger.warning("Out-of-schema arguments for %s; replying.", tool)
            _persist_and_broadcast_reply(conversation, FALLBACK_REPLY)
            return
        try:
            proposal = create_proposal(
                conversation=conversation,
                message=None,
                tool=tool,
                arguments=validated,
                user=conversation.user if conversation.user_id else None,
                guest_key=conversation.guest_key or "",
            )
        except ClarificationRequiredError as exc:
            _persist_and_broadcast_reply(conversation, exc.text)
            return
        emit_action_proposed(
            str(conversation.public_id),
            proposal_id=str(proposal.public_id),
            tool=proposal.tool,
            summary=proposal.summary,
            consequence=proposal.consequence,
            expires_at=proposal.expires_at,
        )
        return

    # Read-only tool: execute silently, summarize, reply (FR-019).
    try:
        result = tool_spec.executor(ctx, arguments)
    except serializers.ValidationError:
        _persist_and_broadcast_reply(conversation, FALLBACK_REPLY)
        return

    output = result.text or ""
    reply = _summarize_tool_output(conversation, history, message.text, output, system_prompt)
    _persist_and_broadcast_reply(conversation, reply)


def _history_before(conversation: Conversation, message_id: str) -> list[dict[str, str]]:
    recent = get_recent_messages(conversation, MAX_HISTORY_MESSAGES)
    history: list[dict[str, str]] = []
    for msg in recent:
        if str(msg.public_id) == message_id:
            continue
        history.append({"role": msg.role, "content": msg.text})
    return history


def _summarize_tool_output(
    conversation: Conversation,
    history: list[dict[str, str]],
    user_text: str,
    output: str,
    system_prompt: str,
) -> str:
    """Second model turn summarizing a read-only tool result (US-1)."""
    summary_prompt = (
        f"{system_prompt}\n"
        "The tool above returned live data. Reply to the guest with a friendly, "
        "concise answer based only on that data."
    )
    messages = ollama.build_chat_messages(
        system_prompt=summary_prompt,
        history=history,
        latest_user_text=user_text,
        tool_output=output,
    )
    try:
        envelope = asyncio.run(
            ollama.generate_envelope(
                system_prompt=summary_prompt,
                messages=messages,
                model=ollama.default_model(),
                url=ollama.default_url(),
            )
        )
    except (ollama.OllamaUnavailableError, ollama.MalformedOutputError):
        return output[:1000] or FALLBACK_REPLY
    if envelope.get("kind") == "reply" and envelope.get("text"):
        return str(envelope["text"])
    return output[:1000] or FALLBACK_REPLY


def _tool_allowed_for_turn(tool: str, offered: list[str], persona: str) -> bool:
    if tool not in offered:
        return False
    return registry.is_allowed(tool, persona)


def _persist_and_broadcast_reply(conversation: Conversation, text: str) -> None:
    reply = Message.objects.create(
        conversation=conversation,
        role=MessageRole.ASSISTANT,
        text=text[:4000],
    )
    emit_assistant_message(
        str(conversation.public_id),
        message_id=str(reply.public_id),
        role=reply.role,
        text=reply.text,
        created_at=reply.created_at,
    )


__all__ = [
    "FALLBACK_REPLY",
    "ingest_message",
    "process_turn",
]

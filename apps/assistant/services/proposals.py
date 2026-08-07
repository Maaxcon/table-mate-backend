from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from common.exceptions import DomainError

from ..models import Message, ProposalStatus, ToolCall, ToolProposal
from ..selectors import get_owned_proposal, get_pending_proposal
from .events import emit_action_result
from .registry import registry

logger = logging.getLogger(__name__)

_PROPOSAL_TTL_SECONDS = 300


class ProposalConflictError(DomainError):
    default_detail = "The proposal cannot be processed in its current state."
    default_code = "proposal_already_processed"
    default_status_code = 409


class ProposalExpiredError(DomainError):
    default_detail = "The proposal has expired."
    default_code = "proposal_expired"
    default_status_code = 409


class ClarificationRequiredError(Exception):
    """The write tool needs more information before it can propose (US-3/AS-4).

    Not a DomainError: it must never surface as a 4xx to the API client.
    The pipeline intercepts it and replies to the guest with ``text``.
    """

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


def proposal_ttl() -> int:
    return int(getattr(settings, "ASSISTANT_PROPOSAL_TTL_SECONDS", _PROPOSAL_TTL_SECONDS))


def _expires_at() -> Any:
    return timezone.now() + timezone.timedelta(seconds=proposal_ttl())


def _json_safe(value: Any) -> Any:
    """Recursively coerce validated (date/time/Decimal/uuid) args to JSON-safe
    values so ``parameters`` survives the JSONField round-trip."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


@transaction.atomic
def create_proposal(
    *,
    conversation,
    message: Message | None,
    tool: str,
    arguments: dict[str, Any],
    user,
    guest_key: str,
) -> ToolProposal:
    """Persist a write-tool proposal with a 5-minute expiry (FR-024).

    At most one pending proposal per conversation (DB partial unique); a
    conflicting pending proposal raises ``ProposalConflictError``. When the
    write tool needs more information before it can propose (US-3/AS-4),
    :class:`ClarificationRequiredError` is raised and no proposal is stored.
    """
    tool_spec = registry.get(tool)
    if tool_spec is None:
        raise DomainError(f"Unknown tool: {tool}")

    pending = get_pending_proposal(conversation)
    if pending is not None:
        raise ProposalConflictError("There is already a pending proposal for this conversation.")

    summary, consequence = _build_proposal_text(tool_spec, arguments, conversation)

    return ToolProposal.objects.create(
        conversation=conversation,
        message=message,
        user=user,
        guest_key=guest_key,
        tool=tool,
        parameters=_json_safe(arguments),
        summary=summary,
        consequence=consequence,
        status=ProposalStatus.PENDING,
        expires_at=_expires_at(),
    )


def _build_proposal_text(tool_spec, arguments: dict[str, Any], conversation) -> tuple[str, str]:
    try:
        result = tool_spec.executor(
            _context_from_conversation(conversation),
            arguments,
        )
        if result.clarification:
            raise ClarificationRequiredError(result.clarification)
        if result.summary:
            return result.summary, result.consequence
    except ClarificationRequiredError:
        raise
    except Exception:
        logger.warning("Proposal text builder fell back for tool %s.", tool_spec.name, exc_info=True)
    return f"Execute {tool_spec.name}", "This performs the requested action."


def _context_from_conversation(conversation):
    from .identity import OwnerIdentity
    from .registry import ToolContext

    return ToolContext(
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


def confirm_proposal(
    proposal_id: str,
    *,
    restaurant_id: int,
    user,
    guest_key: str,
) -> dict[str, Any]:
    """Confirm and execute a pending proposal (idempotent on proposal_id).

    Only a ``pending -> confirmed`` transition may execute (SC-006). Returns the
    recorded result for duplicate confirms; raises for rejected/expired.
    """
    proposal = get_owned_proposal(proposal_id, restaurant_id, user, guest_key)
    if proposal is None:
        from common.exceptions import ReservationNotFoundError

        raise ReservationNotFoundError(f"Proposal {proposal_id} not found.")

    locked = ToolProposal.objects.select_for_update().get(pk=proposal.pk)

    if locked.status == ProposalStatus.EXECUTED:
        return _recorded_result(locked)
    if locked.status == ProposalStatus.CONFIRMED:
        return _recorded_result(locked)
    if locked.status in {ProposalStatus.REJECTED, ProposalStatus.EXPIRED}:
        raise ProposalConflictError(f"Proposal is already {locked.status}.")

    if timezone.now() > locked.expires_at:
        # Commit the expiry mark in its own atomic block that exits BEFORE the
        # raise, so an outer rollback never swallows the recorded expiry.
        with transaction.atomic():
            locked.status = ProposalStatus.EXPIRED
            locked.save(update_fields=["status", "updated_at"])
        raise ProposalExpiredError()

    with transaction.atomic():
        locked = ToolProposal.objects.select_for_update().get(pk=locked.pk)
        locked.status = ProposalStatus.CONFIRMED
        locked.save(update_fields=["status", "updated_at"])

        tool_spec = registry.get(locked.tool)
        if tool_spec is None or tool_spec.execute is None:
            raise DomainError(f"Tool {locked.tool} cannot be executed.")

        result = tool_spec.execute(_context_from_conversation(locked.conversation), locked.parameters)

        locked.status = ProposalStatus.EXECUTED
        locked.save(update_fields=["status", "updated_at"])

        ToolCall.objects.create(
            restaurant_id=restaurant_id,
            conversation=locked.conversation,
            proposal=locked,
            user=user,
            guest_key=guest_key,
            channel="assistant",
            tool=locked.tool,
            parameters=locked.parameters,
            outcome=result.outcome,
            error_code=result.error_code,
            reference_id=result.reference_id or "",
        )

    transaction.on_commit(
        lambda: emit_action_result(
            str(locked.conversation.public_id),
            proposal_id=str(locked.public_id),
            tool=locked.tool,
            outcome=result.outcome,
            reference_id=result.reference_id,
        )
    )

    return {
        "proposal_id": str(locked.public_id),
        "tool": locked.tool,
        "outcome": result.outcome,
        "reference_id": result.reference_id,
        "error_code": result.error_code,
    }


def _recorded_result(proposal: ToolProposal) -> dict[str, Any]:
    call = proposal.tool_calls.order_by("-executed_at").first()
    if call is not None:
        return {
            "proposal_id": str(proposal.public_id),
            "tool": proposal.tool,
            "outcome": call.outcome,
            "reference_id": call.reference_id or None,
            "error_code": call.error_code,
        }
    return {
        "proposal_id": str(proposal.public_id),
        "tool": proposal.tool,
        "outcome": "failed",
        "reference_id": None,
        "error_code": "unknown",
    }


@transaction.atomic
def reject_proposal(
    proposal_id: str,
    *,
    restaurant_id: int,
    user,
    guest_key: str,
) -> ToolProposal:
    """Dismiss a pending proposal; never executes (FR-019)."""
    proposal = get_owned_proposal(proposal_id, restaurant_id, user, guest_key)
    if proposal is None:
        from common.exceptions import ReservationNotFoundError

        raise ReservationNotFoundError(f"Proposal {proposal_id} not found.")

    locked = ToolProposal.objects.select_for_update().get(pk=proposal.pk)
    if locked.status != ProposalStatus.PENDING:
        raise ProposalConflictError(f"Proposal is already {locked.status}.")

    locked.status = ProposalStatus.REJECTED
    locked.save(update_fields=["status", "updated_at"])

    from ..tasks import assistant_followup

    transaction.on_commit(
        lambda: assistant_followup.delay(str(locked.conversation.public_id), str(locked.public_id))
    )

    return locked


def expire_stale_proposals() -> int:
    now = timezone.now()
    updated = 0
    for proposal in ToolProposal.objects.filter(status=ProposalStatus.PENDING, expires_at__lte=now).iterator():
        proposal.status = ProposalStatus.EXPIRED
        proposal.save(update_fields=["status", "updated_at"])
        updated += 1
    return updated


__all__ = [
    "ProposalConflictError",
    "ProposalExpiredError",
    "confirm_proposal",
    "create_proposal",
    "expire_stale_proposals",
    "proposal_ttl",
    "reject_proposal",
]

# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.assistant.models import Conversation, ProposalStatus, ToolCall, ToolOutcome
from apps.assistant.services.proposals import expire_stale_proposals
from apps.assistant.tasks import assistant_cleanup

pytestmark = pytest.mark.django_db


def _create_tool_call(conversation: Any, *, days_old: int) -> ToolCall:
    call = ToolCall.objects.create(
        restaurant_id=conversation.restaurant_id,
        conversation=conversation,
        user=conversation.user if conversation.user_id else None,
        guest_key=conversation.guest_key or "",
        channel="assistant",
        tool="create_reservation",
        parameters={},
        outcome=ToolOutcome.SUCCESS,
        error_code="",
        reference_id="",
    )
    ToolCall.objects.filter(pk=call.pk).update(executed_at=timezone.now() - timedelta(days=days_old))
    return call


class TestRetention:
    def test_cleanup_deletes_old_conversations_and_keeps_recent(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:ret-1")
        old = make_conversation(restaurant, owner)
        recent = make_conversation(restaurant, make_owner(user=None, guest_key="guest:ret-2"))

        from django.test.utils import freeze_time

        with freeze_time(timezone.now() - timedelta(days=8)):
            Conversation.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=8))

        result = assistant_cleanup()
        assert result["conversations_deleted"] >= 1
        assert not Conversation.objects.filter(pk=old.pk).exists()
        assert Conversation.objects.filter(pk=recent.pk).exists()

    def test_cleanup_deletes_old_tool_calls_keeps_recent(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:ret-audit")
        conversation = make_conversation(restaurant, owner)
        old_call = _create_tool_call(conversation, days_old=31)
        recent_call = _create_tool_call(conversation, days_old=5)

        result = assistant_cleanup()
        assert result["toolcalls_deleted"] >= 1
        assert not ToolCall.objects.filter(pk=old_call.pk).exists()
        assert ToolCall.objects.filter(pk=recent_call.pk).exists()

    def test_cleanup_expires_stale_pending_proposals(
        self,
        make_conversation: Any,
        make_owner: Any,
        make_proposal: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:ret-prop")
        conversation = make_conversation(restaurant, owner)
        stale = make_proposal(conversation, expires_in=timedelta(minutes=-1))
        other_conversation = make_conversation(restaurant, make_owner(user=None, guest_key="guest:ret-prop-2"))
        live = make_proposal(other_conversation, expires_in=timedelta(minutes=5))

        result = assistant_cleanup()
        assert result["stale_proposals_expired"] >= 1
        stale.refresh_from_db()
        assert stale.status == ProposalStatus.EXPIRED
        live.refresh_from_db()
        assert live.status == ProposalStatus.PENDING


class TestExpireStaleProposals:
    def test_lazy_expiry_marks_expired_proposals(
        self,
        make_conversation: Any,
        make_owner: Any,
        make_proposal: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:lazy-1")
        conversation = make_conversation(restaurant, owner)
        proposal = make_proposal(conversation, expires_in=timedelta(minutes=-2))

        assert expire_stale_proposals() == 1
        proposal.refresh_from_db()
        assert proposal.status == ProposalStatus.EXPIRED

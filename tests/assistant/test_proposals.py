# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.assistant.models import Message, ProposalStatus, ToolCall, ToolOutcome, ToolProposal
from apps.assistant.services.proposals import (
    ClarificationRequiredError,
    ProposalConflictError,
    ProposalExpiredError,
    confirm_proposal,
    create_proposal,
    reject_proposal,
)
from apps.menu.models import ModifierGroup, ModifierOption
from apps.reservations.models import ReservationStatus
from common.exceptions import ReservationNotFoundError

pytestmark = pytest.mark.django_db


def _reservation(restaurant: Any, table: Any, customer: Any) -> Any:
    from apps.reservations.models import Reservation

    return Reservation.objects.create(
        restaurant=restaurant,
        table=table,
        customer=customer,
        guest_count=2,
        start_at=timezone.now() + timedelta(days=1),
        end_at=timezone.now() + timedelta(days=1, hours=2),
        status=ReservationStatus.PENDING,
    )


class TestCreateProposal:
    def test_parameters_are_json_safe(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:prop-json")
        conversation = make_conversation(restaurant, owner)

        proposal = create_proposal(
            conversation=conversation,
            message=None,
            tool="create_reservation",
            arguments={"date": timezone.now().date(), "time": "19:00", "party_size": 2},
            user=None,
            guest_key="guest:prop-json",
        )
        proposal.refresh_from_db()
        assert proposal.parameters["date"] == timezone.now().date().isoformat()
        assert proposal.parameters["time"] == "19:00"
        assert proposal.parameters["party_size"] == 2

    def test_second_pending_proposal_conflicts(
        self,
        make_conversation: Any,
        make_owner: Any,
        make_proposal: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:prop-conflict")
        conversation = make_conversation(restaurant, owner)
        make_proposal(conversation, owner=owner)

        with pytest.raises(ProposalConflictError):
            create_proposal(
                conversation=conversation,
                message=None,
                tool="cancel_reservation",
                arguments={},
                user=None,
                guest_key="guest:prop-conflict",
            )

    def test_unknown_tool_rejected(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:prop-unknown")
        conversation = make_conversation(restaurant, owner)
        from common.exceptions import DomainError

        with pytest.raises(DomainError):
            create_proposal(
                conversation=conversation,
                message=None,
                tool="does_not_exist",
                arguments={},
                user=None,
                guest_key="guest:prop-unknown",
            )

    def test_missing_required_modifier_raises_clarification_not_proposal(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
        item: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:prop-clarify")
        conversation = make_conversation(restaurant, owner)
        group = ModifierGroup.objects.create(menu_item=item, restaurant=restaurant, name="Size", is_required=True)
        ModifierOption.objects.create(group=group, restaurant=restaurant, name="Large")

        with pytest.raises(ClarificationRequiredError) as excinfo:
            create_proposal(
                conversation=conversation,
                message=None,
                tool="add_to_cart",
                arguments={"menu_item_id": str(item.public_id), "quantity": 1},
                user=None,
                guest_key="guest:prop-clarify",
            )
        assert "Size" in excinfo.value.text
        assert not ToolProposal.objects.filter(conversation=conversation).exists()

    def test_modifiers_flow_into_stored_proposal_parameters(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
        item: Any,
    ) -> None:
        owner = make_owner(user=None, guest_key="guest:prop-mod")
        conversation = make_conversation(restaurant, owner)
        group = ModifierGroup.objects.create(menu_item=item, restaurant=restaurant, name="Size", is_required=True)
        option = ModifierOption.objects.create(group=group, restaurant=restaurant, name="Large", price_delta="2.00")

        proposal = create_proposal(
            conversation=conversation,
            message=None,
            tool="add_to_cart",
            arguments={
                "menu_item_id": str(item.public_id),
                "quantity": 1,
                "modifiers": [
                    {"modifier_id": str(group.public_id), "option_id": str(option.public_id)},
                ],
            },
            user=None,
            guest_key="guest:prop-mod",
        )
        assert proposal.status == ProposalStatus.PENDING
        assert proposal.parameters["modifiers"] == [
            {"modifier_id": str(group.public_id), "option_id": str(option.public_id)}
        ]


class TestConfirmProposal:
    def test_confirm_executes_and_records_tool_call(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
        table: Any,
        user_factory: Any,
        django_capture_on_commit_callbacks: Any,
    ) -> None:
        user = user_factory()
        user.save()
        reservation = _reservation(restaurant, table, user)
        owner = make_owner(user=user)
        conversation = make_conversation(restaurant, owner)
        proposal = create_proposal(
            conversation=conversation,
            message=None,
            tool="cancel_reservation",
            arguments={"reservation_id": str(reservation.public_id)},
            user=user,
            guest_key="",
        )

        with django_capture_on_commit_callbacks(execute=True):
            result = confirm_proposal(
                proposal_id=str(proposal.public_id),
                restaurant_id=restaurant.id,
                user=user,
                guest_key="",
            )

        assert result["outcome"] == "success"
        assert result["tool"] == "cancel_reservation"
        proposal.refresh_from_db()
        assert proposal.status == ProposalStatus.EXECUTED
        reservation.refresh_from_db()
        assert reservation.status == ReservationStatus.CANCELLED
        call = ToolCall.objects.get(proposal=proposal)
        assert call.outcome == ToolOutcome.SUCCESS
        assert call.channel == "assistant"

    def test_duplicate_confirm_is_idempotent(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
        table: Any,
        user_factory: Any,
        django_capture_on_commit_callbacks: Any,
    ) -> None:
        user = user_factory()
        user.save()
        reservation = _reservation(restaurant, table, user)
        owner = make_owner(user=user)
        conversation = make_conversation(restaurant, owner)
        proposal = create_proposal(
            conversation=conversation,
            message=None,
            tool="cancel_reservation",
            arguments={"reservation_id": str(reservation.public_id)},
            user=user,
            guest_key="",
        )

        with django_capture_on_commit_callbacks(execute=True):
            confirm_proposal(str(proposal.public_id), restaurant_id=restaurant.id, user=user, guest_key="")
        with django_capture_on_commit_callbacks(execute=True):
            again = confirm_proposal(str(proposal.public_id), restaurant_id=restaurant.id, user=user, guest_key="")

        assert again["outcome"] == "success"
        assert again["proposal_id"] == str(proposal.public_id)
        assert ToolCall.objects.filter(proposal=proposal).count() == 1

    def test_expired_proposal_raises(
        self,
        make_conversation: Any,
        make_owner: Any,
        make_proposal: Any,
        restaurant: Any,
        user_factory: Any,
    ) -> None:
        user = user_factory()
        user.save()
        owner = make_owner(user=user)
        conversation = make_conversation(restaurant, owner)
        proposal = make_proposal(conversation, expires_in=timedelta(minutes=-1), owner=owner)

        with pytest.raises(ProposalExpiredError):
            confirm_proposal(str(proposal.public_id), restaurant_id=restaurant.id, user=user, guest_key="")
        proposal.refresh_from_db()
        assert proposal.status == ProposalStatus.EXPIRED

    def test_rejected_proposal_cannot_be_confirmed(
        self,
        make_conversation: Any,
        make_owner: Any,
        make_proposal: Any,
        restaurant: Any,
        user_factory: Any,
    ) -> None:
        user = user_factory()
        user.save()
        owner = make_owner(user=user)
        conversation = make_conversation(restaurant, owner)
        proposal = make_proposal(conversation, status=ProposalStatus.REJECTED, owner=owner)

        with pytest.raises(ProposalConflictError):
            confirm_proposal(str(proposal.public_id), restaurant_id=restaurant.id, user=user, guest_key="")

    def test_other_owner_cannot_confirm(
        self,
        make_conversation: Any,
        make_owner: Any,
        make_proposal: Any,
        restaurant: Any,
        user_factory: Any,
    ) -> None:
        owner_user = user_factory()
        owner_user.save()
        intruder = user_factory()
        intruder.save()
        owner = make_owner(user=owner_user)
        conversation = make_conversation(restaurant, owner)
        proposal = make_proposal(conversation, owner=owner)

        with pytest.raises(ReservationNotFoundError):
            confirm_proposal(str(proposal.public_id), restaurant_id=restaurant.id, user=intruder, guest_key="")


class TestRejectProposal:
    def test_reject_marks_rejected_and_never_executes(
        self,
        make_conversation: Any,
        make_owner: Any,
        restaurant: Any,
        user_factory: Any,
        django_capture_on_commit_callbacks: Any,
    ) -> None:
        user = user_factory()
        user.save()
        owner = make_owner(user=user)
        conversation = make_conversation(restaurant, owner)
        proposal = create_proposal(
            conversation=conversation,
            message=None,
            tool="create_reservation",
            arguments={"date": timezone.now().date().isoformat(), "time": "19:00", "party_size": 2},
            user=user,
            guest_key="",
        )

        with patch("apps.assistant.tasks.assistant_followup") as task, django_capture_on_commit_callbacks(execute=True):
            rejected = reject_proposal(
                proposal_id=str(proposal.public_id),
                restaurant_id=restaurant.id,
                user=user,
                guest_key="",
            )
        assert rejected.status == ProposalStatus.REJECTED
        assert not ToolCall.objects.filter(proposal=proposal).exists()
        assert not Message.objects.filter(conversation=conversation, role="assistant").exists()
        task.delay.assert_called_once_with(str(conversation.public_id), str(proposal.public_id))

    def test_reject_non_pending_conflicts(
        self,
        make_conversation: Any,
        make_owner: Any,
        make_proposal: Any,
        restaurant: Any,
        user_factory: Any,
    ) -> None:
        user = user_factory()
        user.save()
        owner = make_owner(user=user)
        conversation = make_conversation(restaurant, owner)
        proposal = make_proposal(conversation, status=ProposalStatus.EXECUTED, owner=owner)

        with pytest.raises(ProposalConflictError):
            reject_proposal(str(proposal.public_id), restaurant_id=restaurant.id, user=user, guest_key="")

from __future__ import annotations

from typing import Any, cast

from django.http import Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.authentication import GuestJWTAuthentication
from apps.authentication.models import User

from ...models import Conversation
from ...selectors import (
    get_messages,
    get_owned_conversation,
    get_owned_proposal,
    get_pending_proposal,
    get_recent_messages,
)
from ...services.conversations import get_or_create_conversation
from ...services.handoff import create_handoff
from ...services.identity import owner_from_request, require_restaurant_id
from ...services.pipeline import ingest_message
from ...services.proposals import (
    ProposalConflictError,
    ProposalExpiredError,
    confirm_proposal,
    reject_proposal,
)
from ...services.rate_limit import RateLimitExceededError
from .serializers import (
    ConversationCreateSerializer,
    ConversationSerializer,
    HandoffCreateSerializer,
    HandoffResponseSerializer,
    MessageAcceptedSerializer,
    MessageCreateSerializer,
    MessageSerializer,
    ProposalRejectedSerializer,
    ProposalResultSerializer,
)


class GuestFallbackAuthMixin:
    """Accept guest JWTs that the default TokenVersionJWTAuthentication rejects."""

    def perform_authentication(self, request: Request) -> None:
        try:
            super().perform_authentication(request)  # type: ignore[misc]
        except AuthenticationFailed:
            guest = GuestJWTAuthentication()
            result = guest.authenticate(request)
            if result is not None:
                request.user, request.auth = result
            else:
                raise


class AssistantMessagesPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


@extend_schema(tags=["Assistant"])
class ConversationCreateView(GuestFallbackAuthMixin, APIView):
    """Create or resume the guest's conversation (POST /conversations/)."""

    serializer_class = ConversationCreateSerializer

    @extend_schema(
        request=ConversationCreateSerializer,
        responses={201: ConversationSerializer, 403: OpenApiResponse(description="No restaurant scope.")},
    )
    def post(self, request: Request) -> Response:
        serializer = ConversationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        restaurant_id = require_restaurant_id(request)
        owner = owner_from_request(request)
        language = serializer.validated_data.get("language") or None

        conversation = get_or_create_conversation(
            restaurant_id=restaurant_id,
            owner=owner,
            language=language,
        )
        payload = _conversation_payload(conversation)
        return Response(payload, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Assistant"])
class ConversationDetailView(GuestFallbackAuthMixin, APIView):
    """Fetch one owned conversation (GET /conversations/{id}/)."""

    @extend_schema(responses={200: ConversationSerializer, 404: OpenApiResponse(description="Not found.")})
    def get(self, request: Request, conversation_id: str) -> Response:
        conversation = self._get_owned(request, conversation_id)
        return Response(_conversation_payload(conversation))

    def _get_owned(self, request: Request, conversation_id: str) -> Conversation:
        owner = owner_from_request(request)
        conversation = get_owned_conversation(
            conversation_id=conversation_id,
            restaurant_id=require_restaurant_id(request),
            user=cast(User | None, owner.user),
            guest_key=owner.guest_key,
        )
        if conversation is None:
            raise Http404("Conversation not found.")
        return conversation


@extend_schema(tags=["Assistant"])
class ConversationMessagesView(GuestFallbackAuthMixin, APIView):
    """History and new messages for one conversation (GET/POST /conversations/{id}/messages/)."""

    @extend_schema(responses={200: MessageSerializer(many=True)})
    def get(self, request: Request, conversation_id: str) -> Response:
        conversation = self._get_owned(request, conversation_id)
        paginator = AssistantMessagesPagination()
        page = paginator.paginate_queryset(get_messages(conversation), request, view=self)
        return self._paged_response(page or [], paginator)

    @extend_schema(
        request=MessageCreateSerializer,
        responses={
            202: MessageAcceptedSerializer,
            400: OpenApiResponse(description="Empty text or invalid ui_context."),
            429: OpenApiResponse(description="Rate limit exceeded."),
        },
    )
    def post(self, request: Request, conversation_id: str) -> Response:
        conversation = self._get_owned(request, conversation_id)
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        owner = owner_from_request(request)
        try:
            message = ingest_message(
                restaurant_id=require_restaurant_id(request),
                conversation=conversation,
                text=serializer.validated_data["text"],
                owner=owner,
                ui_context=serializer.validated_data.get("ui_context", {}),
            )
        except RateLimitExceededError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        payload = MessageAcceptedSerializer(
            {"message_id": str(message.public_id), "conversation_id": str(conversation.public_id)}
        ).data
        return Response(payload, status=status.HTTP_202_ACCEPTED)

    def _get_owned(self, request: Request, conversation_id: str) -> Conversation:
        owner = owner_from_request(request)
        conversation = get_owned_conversation(
            conversation_id=conversation_id,
            restaurant_id=require_restaurant_id(request),
            user=cast(User | None, owner.user),
            guest_key=owner.guest_key,
        )
        if conversation is None:
            raise Http404("Conversation not found.")
        return conversation

    def _paged_response(self, page: list[Any], paginator: AssistantMessagesPagination) -> Response:
        payload = [
            {
                "message_id": str(m.public_id),
                "role": m.role,
                "text": m.text,
                "created_at": m.created_at,
            }
            for m in page
        ]
        serializer = MessageSerializer(payload, many=True)
        return Response(
            {
                "count": paginator.page.paginator.count if paginator.page is not None else 0,
                "next": paginator.get_next_link(),
                "results": serializer.data,
            }
        )


@extend_schema(tags=["Assistant"])
class ProposalConfirmView(GuestFallbackAuthMixin, APIView):
    """Confirm a pending proposal (POST /proposals/{id}/confirm/)."""

    @extend_schema(
        responses={200: ProposalResultSerializer, 409: OpenApiResponse(description="Expired or already handled.")}
    )
    def post(self, request: Request, proposal_id: str) -> Response:
        proposal = self._get_owned(request, proposal_id)
        owner = owner_from_request(request)
        try:
            result = confirm_proposal(
                proposal_id=str(proposal.public_id),
                restaurant_id=require_restaurant_id(request),
                user=cast(User | None, owner.user),
                guest_key=owner.guest_key,
            )
        except (ProposalExpiredError, ProposalConflictError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(ProposalResultSerializer(result).data)

    def _get_owned(self, request: Request, proposal_id: str) -> Any:
        owner = owner_from_request(request)
        proposal = get_owned_proposal(
            proposal_id=proposal_id,
            restaurant_id=require_restaurant_id(request),
            user=cast(User | None, owner.user),
            guest_key=owner.guest_key,
        )
        if proposal is None:
            raise Http404("Proposal not found.")
        return proposal


@extend_schema(tags=["Assistant"])
class ProposalRejectView(GuestFallbackAuthMixin, APIView):
    """Dismiss a pending proposal (POST /proposals/{id}/reject/)."""

    @extend_schema(responses={200: ProposalRejectedSerializer, 409: OpenApiResponse(description="Already handled.")})
    def post(self, request: Request, proposal_id: str) -> Response:
        proposal = self._get_owned(request, proposal_id)
        owner = owner_from_request(request)
        try:
            reject_proposal(
                proposal_id=str(proposal.public_id),
                restaurant_id=require_restaurant_id(request),
                user=cast(User | None, owner.user),
                guest_key=owner.guest_key,
            )
        except ProposalConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(ProposalRejectedSerializer({"proposal_id": proposal_id, "status": "rejected"}).data)

    def _get_owned(self, request: Request, proposal_id: str) -> Any:
        owner = owner_from_request(request)
        proposal = get_owned_proposal(
            proposal_id=proposal_id,
            restaurant_id=require_restaurant_id(request),
            user=cast(User | None, owner.user),
            guest_key=owner.guest_key,
        )
        if proposal is None:
            raise Http404("Proposal not found.")
        return proposal


@extend_schema(tags=["Assistant"])
class HandoffView(GuestFallbackAuthMixin, APIView):
    """Request staff assistance (POST /conversations/{id}/handoff/)."""

    @extend_schema(
        request=HandoffCreateSerializer,
        responses={201: HandoffResponseSerializer, 404: OpenApiResponse(description="Not found.")},
    )
    def post(self, request: Request, conversation_id: str) -> Response:
        owner = owner_from_request(request)
        conversation = get_owned_conversation(
            conversation_id=conversation_id,
            restaurant_id=require_restaurant_id(request),
            user=cast(User | None, owner.user),
            guest_key=owner.guest_key,
        )
        if conversation is None:
            raise Http404("Conversation not found.")

        serializer = HandoffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        handoff = create_handoff(
            conversation=conversation,
            reason=serializer.validated_data.get("reason") or "",
        )
        return Response(
            HandoffResponseSerializer(
                {
                    "handoff_id": str(handoff.public_id),
                    "status": handoff.status,
                    "notified_at": handoff.notified_at.isoformat() if handoff.notified_at else None,
                }
            ).data,
            status=status.HTTP_201_CREATED,
        )


def _conversation_payload(conversation: Conversation) -> dict[str, Any]:
    recent = get_recent_messages(conversation, limit=10)
    pending = get_pending_proposal(conversation)
    return ConversationSerializer(
        {
            "conversation_id": str(conversation.public_id),
            "status": conversation.status,
            "language": conversation.language,
            "created_at": conversation.created_at,
            "recent_messages": [
                {"message_id": str(m.public_id), "role": m.role, "text": m.text, "created_at": m.created_at}
                for m in recent
            ],
            "pending_proposal": (
                {
                    "proposal_id": str(pending.public_id),
                    "tool": pending.tool,
                    "summary": pending.summary,
                    "consequence": pending.consequence,
                    "expires_at": pending.expires_at,
                }
                if pending is not None
                else None
            ),
        }
    ).data


__all__ = [
    "AssistantMessagesPagination",
    "ConversationCreateView",
    "ConversationDetailView",
    "ConversationMessagesView",
    "HandoffView",
    "ProposalConfirmView",
    "ProposalRejectView",
]

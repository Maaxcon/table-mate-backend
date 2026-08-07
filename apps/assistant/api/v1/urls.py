from django.urls import path

from .views import (
    ConversationCreateView,
    ConversationDetailView,
    ConversationMessagesView,
    HandoffView,
    ProposalConfirmView,
    ProposalRejectView,
)

urlpatterns = [
    path("conversations/", ConversationCreateView.as_view(), name="assistant-conversation-create"),
    path(
        "conversations/<str:conversation_id>/",
        ConversationDetailView.as_view(),
        name="assistant-conversation-detail",
    ),
    path(
        "conversations/<str:conversation_id>/messages/",
        ConversationMessagesView.as_view(),
        name="assistant-conversation-messages",
    ),
    path(
        "conversations/<str:conversation_id>/handoff/",
        HandoffView.as_view(),
        name="assistant-conversation-handoff",
    ),
    path(
        "proposals/<str:proposal_id>/confirm/",
        ProposalConfirmView.as_view(),
        name="assistant-proposal-confirm",
    ),
    path(
        "proposals/<str:proposal_id>/reject/",
        ProposalRejectView.as_view(),
        name="assistant-proposal-reject",
    ),
]

__all__ = ["urlpatterns"]

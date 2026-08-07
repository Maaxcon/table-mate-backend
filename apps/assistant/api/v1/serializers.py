from __future__ import annotations

from typing import Any

from rest_framework import serializers


class ConversationCreateSerializer(serializers.Serializer):
    language = serializers.CharField(required=False, allow_blank=True, max_length=10)


class MessageCreateSerializer(serializers.Serializer):
    text = serializers.CharField(min_length=1, max_length=2000)
    ui_context = serializers.JSONField(required=False, default=dict)

    def validate_text(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Message text must not be empty.")
        return stripped

    def validate_ui_context(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("ui_context must be a JSON object.")
        return value


class MessageSerializer(serializers.Serializer):
    message_id = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    text = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class PendingProposalSerializer(serializers.Serializer):
    proposal_id = serializers.CharField(read_only=True)
    tool = serializers.CharField(read_only=True)
    summary = serializers.CharField(read_only=True)
    consequence = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)


class ConversationSerializer(serializers.Serializer):
    conversation_id = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    language = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    recent_messages = MessageSerializer(many=True, read_only=True)
    pending_proposal = PendingProposalSerializer(read_only=True, allow_null=True)


class MessageAcceptedSerializer(serializers.Serializer):
    message_id = serializers.CharField(read_only=True)
    conversation_id = serializers.CharField(read_only=True)


class ProposalResultSerializer(serializers.Serializer):
    proposal_id = serializers.CharField(read_only=True)
    tool = serializers.CharField(read_only=True)
    outcome = serializers.CharField(read_only=True)
    reference_id = serializers.CharField(read_only=True, allow_null=True)
    error_code = serializers.CharField(read_only=True, allow_blank=True)


class ProposalRejectedSerializer(serializers.Serializer):
    proposal_id = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)


class HandoffCreateSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class HandoffResponseSerializer(serializers.Serializer):
    handoff_id = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    notified_at = serializers.DateTimeField(read_only=True, allow_null=True)


__all__ = [
    "ConversationCreateSerializer",
    "ConversationSerializer",
    "HandoffCreateSerializer",
    "HandoffResponseSerializer",
    "MessageAcceptedSerializer",
    "MessageCreateSerializer",
    "MessageSerializer",
    "PendingProposalSerializer",
    "ProposalRejectedSerializer",
    "ProposalResultSerializer",
]

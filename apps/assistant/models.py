from django.db import models

from common.models import BaseModel, RestaurantScopedModel


class ConversationStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CLOSED = "closed", "Closed"


class MessageRole(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"


class ProposalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    EXECUTED = "executed", "Executed"


class ToolOutcome(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class HandoffStatus(models.TextChoices):
    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"


class Conversation(RestaurantScopedModel):
    """Persistent chat session. Exactly one of `user` / `guest_key` is set."""

    user = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_conversations",
    )
    guest_key = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ConversationStatus.choices,
        default=ConversationStatus.ACTIVE,
    )
    language = models.CharField(max_length=10, default="uk")

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=False, guest_key="")
                | models.Q(user__isnull=True, guest_key__gt=""),
                name="assistant_conversation_owner_xor",
            ),
            models.UniqueConstraint(
                fields=["restaurant", "user"],
                condition=models.Q(user__isnull=False),
                name="assistant_conversation_one_per_user",
            ),
            models.UniqueConstraint(
                fields=["restaurant", "guest_key"],
                condition=~models.Q(guest_key=""),
                name="assistant_conversation_one_per_guest",
            ),
        ]
        indexes = [
            models.Index(fields=["restaurant", "updated_at"]),
        ]

    def __str__(self) -> str:
        return f"Conversation {self.public_id}"

    def clean(self) -> None:
        if bool(self.user) == bool(self.guest_key):
            raise ValueError("exactly one of user or guest_key must be set")


class Message(BaseModel):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=20, choices=MessageRole.choices)
    text = models.TextField()

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.role} message in {self.conversation.public_id}"


class ToolProposal(BaseModel):
    """Pending action awaiting guest confirmation. `public_id` is the idempotency key."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="proposals",
    )
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="proposals",
    )
    user = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_proposals",
    )
    guest_key = models.CharField(max_length=255, blank=True)
    tool = models.CharField(max_length=64)
    parameters = models.JSONField(default=dict)
    summary = models.TextField()
    consequence = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=ProposalStatus.choices,
        default=ProposalStatus.PENDING,
    )
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(user__isnull=False, guest_key="")
                | models.Q(user__isnull=True, guest_key__gt=""),
                name="assistant_toolproposal_owner_xor",
            ),
            models.UniqueConstraint(
                fields=["conversation"],
                condition=models.Q(status=ProposalStatus.PENDING),
                name="assistant_toolproposal_one_pending",
            ),
        ]
        indexes = [
            models.Index(fields=["conversation", "status"]),
        ]

    def __str__(self) -> str:
        return f"Proposal {self.public_id} for {self.tool}"

    def clean(self) -> None:
        if bool(self.user) == bool(self.guest_key):
            raise ValueError("exactly one of user or guest_key must be set")


class ToolCall(RestaurantScopedModel):
    """Audit record of an executed tool; survives conversation deletion."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tool_calls",
    )
    proposal = models.ForeignKey(
        ToolProposal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tool_calls",
    )
    user = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_tool_calls",
    )
    guest_key = models.CharField(max_length=255, blank=True)
    channel = models.CharField(max_length=32, default="assistant")
    tool = models.CharField(max_length=64)
    parameters = models.JSONField(default=dict)
    outcome = models.CharField(max_length=20, choices=ToolOutcome.choices)
    error_code = models.CharField(max_length=64, blank=True)
    reference_id = models.CharField(max_length=255, blank=True)
    executed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-executed_at", "-id"]
        indexes = [
            models.Index(fields=["restaurant", "executed_at"]),
            models.Index(fields=["proposal"]),
        ]

    def __str__(self) -> str:
        return f"ToolCall {self.public_id}: {self.tool} ({self.outcome})"


class HandoffRequest(RestaurantScopedModel):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="handoff_requests",
    )
    status = models.CharField(
        max_length=20,
        choices=HandoffStatus.choices,
        default=HandoffStatus.OPEN,
    )
    context_summary = models.TextField()
    notes = models.TextField(blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["restaurant", "status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Handoff {self.public_id} ({self.status})"

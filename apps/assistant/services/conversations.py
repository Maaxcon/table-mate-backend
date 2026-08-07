from __future__ import annotations

from apps.restaurants.models import RestaurantSettings

from ..models import Conversation, ConversationStatus
from .identity import OwnerIdentity


def default_language(restaurant_id: int) -> str:
    settings = RestaurantSettings.objects.filter(restaurant_id=restaurant_id).first()
    if settings is not None:
        supported = settings.supported_languages or []
        if settings.locale and settings.locale in supported:
            return settings.locale
        if supported:
            return supported[0]
        if settings.locale:
            return settings.locale
    return "uk"


def get_or_create_conversation(
    *,
    restaurant_id: int,
    owner: OwnerIdentity,
    language: str | None = None,
) -> Conversation:
    """Return the guest's existing conversation for this restaurant, or create one.

    The partial-unique indexes in the model enforce a single conversation per
    owner per restaurant; a race between two concurrent creates surfaces as an
    IntegrityError, which we resolve by re-reading the winner.
    """
    from django.db import IntegrityError

    filters: dict[str, object] = {"restaurant_id": restaurant_id}
    if owner.user is not None:
        filters["user"] = owner.user
    else:
        filters["guest_key"] = owner.guest_key

    existing = Conversation.objects.filter(**filters).first()
    if existing is not None:
        return existing

    try:
        return Conversation.objects.create(
            restaurant_id=restaurant_id,
            user=owner.user if owner.user is not None else None,
            guest_key=owner.guest_key if owner.guest_key else "",
            language=language or default_language(restaurant_id),
            status=ConversationStatus.ACTIVE,
        )
    except IntegrityError:
        return Conversation.objects.filter(**filters).get()


def get_owned_conversation(
    conversation_id: str,
    restaurant_id: int,
    owner: OwnerIdentity,
) -> Conversation | None:
    from ..selectors import get_owned_conversation as _get_owned

    return _get_owned(
        conversation_id,
        restaurant_id,
        owner.user if owner.user is not None else None,
        owner.guest_key,
    )


__all__ = ["default_language", "get_or_create_conversation", "get_owned_conversation"]

from __future__ import annotations

import uuid

from .models import Session


def get_session(session_id: uuid.UUID, restaurant_id: int) -> Session | None:
    """Return the restaurant's session by public id, or None if it doesn't exist."""
    return Session.objects.filter(public_id=session_id, restaurant_id=restaurant_id).first()

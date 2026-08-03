from typing import Any
from uuid import uuid4

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.authentication.models import User

from .models import Feedback


@receiver(pre_delete, sender=User)
def _anonymize_feedback_on_user_delete(sender: type[User], instance: User, **kwargs: Any) -> None:
    """Detach a deleted user's feedback without losing the ratings.

    Feedback.guest is SET_NULL, but the ``feedback_single_owner`` check
    constraint requires exactly one of guest/guest_identity. Authenticated
    feedback has guest set and guest_identity NULL, so a plain SET_NULL would
    leave both NULL and abort the user's deletion with IntegrityError. Move the
    row to the anonymous-guest branch (guest_identity set, guest NULL) in a
    single atomic UPDATE so the constraint never sees an invalid intermediate.
    """
    Feedback.objects.filter(guest=instance).update(guest=None, guest_identity=str(uuid4()))

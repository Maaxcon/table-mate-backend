from django.db.models import F
from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import User


@receiver(pre_save, sender=User)
def invalidate_tokens_on_role_or_restaurant_change(sender: type[User], instance: User, **kwargs: object) -> None:
    if not instance.pk:
        return
    try:
        db = User.objects.values("role", "restaurant_id", "token_version").get(pk=instance.pk)
    except User.DoesNotExist:
        return
    if db["role"] != instance.role or db["restaurant_id"] != instance.restaurant_id:
        # Atomic increment in DB, then reflect the new value on the instance so
        # token generation that runs after save reads the correct version.
        User.objects.filter(pk=instance.pk).update(token_version=F("token_version") + 1)
        instance.token_version = db["token_version"] + 1

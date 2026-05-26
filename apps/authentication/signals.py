from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import User


@receiver(pre_save, sender=User)
def invalidate_tokens_on_role_or_restaurant_change(sender: type[User], instance: User, **kwargs: object) -> None:
    if not instance.pk:
        return
    try:
        db = User.objects.values("role", "restaurant_id").get(pk=instance.pk)
    except User.DoesNotExist:
        return
    if db["role"] != instance.role or db["restaurant_id"] != instance.restaurant_id:
        instance.token_version += 1

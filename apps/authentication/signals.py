from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import User


@receiver(pre_save, sender=User)
def invalidate_tokens_on_role_change(sender: type[User], instance: User, **kwargs: object) -> None:
    if not instance.pk:
        return
    try:
        current_role = User.objects.values_list("role", flat=True).get(pk=instance.pk)
    except User.DoesNotExist:
        return
    if current_role != instance.role:
        instance.token_version += 1

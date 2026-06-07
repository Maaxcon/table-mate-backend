from typing import Any

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from common.files import delete_file_on_delete, delete_old_file_on_change

from .models import Restaurant


@receiver(pre_save, sender=Restaurant)
def _restaurant_delete_replaced_cover(sender: type[Restaurant], instance: Restaurant, **kwargs: Any) -> None:
    delete_old_file_on_change(sender, instance, "cover_image")


@receiver(post_delete, sender=Restaurant)
def _restaurant_delete_cover(sender: type[Restaurant], instance: Restaurant, **kwargs: Any) -> None:
    delete_file_on_delete(instance, "cover_image")

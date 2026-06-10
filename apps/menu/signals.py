from typing import Any

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from common.files import delete_file_on_delete, delete_old_file_on_change

from .models import MenuItem


@receiver(pre_save, sender=MenuItem)
def _menu_item_delete_replaced_image(sender: type[MenuItem], instance: MenuItem, **kwargs: Any) -> None:
    delete_old_file_on_change(sender, instance, "image")


@receiver(post_delete, sender=MenuItem)
def _menu_item_delete_image(sender: type[MenuItem], instance: MenuItem, **kwargs: Any) -> None:
    delete_file_on_delete(instance, "image")

from typing import Any

from django.db.models import Model


def delete_old_file_on_change(sender: type[Model], instance: Model, field_name: str) -> None:
    """Delete the previously stored file when an instance's file field changes.

    Meant for a pre_save signal: Django keeps the old file on disk when a
    FileField/ImageField is replaced or cleared, so we remove it by hand.
    """
    if not instance.pk:
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    old_file = getattr(old, field_name)
    new_file: Any = getattr(instance, field_name)
    if old_file and old_file.name != getattr(new_file, "name", None):
        old_file.delete(save=False)


def delete_file_on_delete(instance: Model, field_name: str) -> None:
    """Delete an instance's stored file when the row is deleted (post_delete)."""
    file = getattr(instance, field_name)
    if file:
        file.delete(save=False)

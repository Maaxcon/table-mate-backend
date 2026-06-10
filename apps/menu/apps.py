from django.apps import AppConfig


class MenuConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.menu"
    label = "menu"

    def ready(self) -> None:
        from . import signals  # noqa: F401  (registers image-cleanup signals)

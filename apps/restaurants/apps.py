from django.apps import AppConfig


class RestaurantsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.restaurants"
    label = "restaurants"

    def ready(self) -> None:
        from . import signals  # noqa: F401  (registers cover-image cleanup signals)

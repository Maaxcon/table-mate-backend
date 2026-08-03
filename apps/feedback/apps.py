from django.apps import AppConfig


class FeedbackConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.feedback"
    label = "feedback"

    def ready(self) -> None:
        from . import signals  # noqa: F401  (anonymize feedback when a user account is deleted)

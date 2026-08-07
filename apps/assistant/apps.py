from django.apps import AppConfig


class AssistantConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assistant"
    verbose_name = "AI Guest Assistant"

    def ready(self) -> None:
        # Importing the module runs the registry.register_tool(...) calls at
        # module level — without this the tool registry is empty at runtime.
        from .services import tools  # noqa: F401

from typing import Any

from django.conf import settings
from django.core.checks import Warning, register


@register()
def google_oauth_settings_check(app_configs: Any, **kwargs: Any) -> list[Warning]:
    warnings: list[Warning] = []
    for name, check_id in (
        ("GOOGLE_CLIENT_ID", "authentication.W001"),
        ("GOOGLE_CLIENT_SECRET", "authentication.W002"),
    ):
        if not getattr(settings, name, ""):
            warnings.append(
                Warning(
                    f"{name} is not set; Google login will fail for every user.",
                    hint=f"Set the {name} environment variable.",
                    id=check_id,
                )
            )
    return warnings

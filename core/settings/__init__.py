import os
from importlib import import_module

settings_module = os.getenv("DJANGO_SETTINGS_MODULE", "")


if settings_module in {"", "core.settings"}:
    env = os.getenv("DJANGO_ENV", "local").lower()
    target_module = (
        "core.settings.production" if env == "production" else "core.settings.local"
    )

    module = import_module(target_module)

    for setting_name in dir(module):
        if setting_name.isupper():
            globals()[setting_name] = getattr(module, setting_name)

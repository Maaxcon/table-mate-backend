import os
from importlib import import_module

ENV = os.getenv("DJANGO_ENV", "local").lower()
TARGET_MODULE = "core.settings.production" if ENV == "production" else "core.settings.local"

module = import_module(TARGET_MODULE)

for setting_name in dir(module):
    if setting_name.isupper():
        globals()[setting_name] = getattr(module, setting_name)

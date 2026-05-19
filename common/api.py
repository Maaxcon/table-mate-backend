from typing import ClassVar


class PublicLookupMixin:
    lookup_field: ClassVar[str] = "public_id"
    lookup_url_kwarg: ClassVar[str | None] = "public_id"
    lookup_value_regex: ClassVar[str] = "[0-9a-fA-F-]{36}"

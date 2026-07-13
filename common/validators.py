from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

ALLOWED_IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_IMAGE_MIMES: set[str] = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# Magic bytes for image format detection (first bytes of file content).
_IMAGE_MAGIC: dict[str, list[bytes]] = {
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "gif": [b"GIF87a", b"GIF89a"],
    "webp": [b"RIFF"],
}


def validate_image_magic(content: bytes) -> None:
    if not content:
        raise ValidationError(_("Empty file."), code="empty_file")
    for image_type, signatures in _IMAGE_MAGIC.items():
        for sig in signatures:
            if content.startswith(sig):
                if image_type == "webp":
                    if len(content) >= 12 and content[8:12] == b"WEBP":
                        return
                    continue
                return
    raise ValidationError(_("Invalid image type. Allowed: JPEG, PNG, GIF, WebP."), code="invalid_image")


@deconstructible
class MaxFileSizeValidator:
    limit: int

    def __init__(self, max_size_mb: int = 5) -> None:
        self.limit = max_size_mb * 1024 * 1024

    def __call__(self, file: object) -> None:
        if hasattr(file, "size") and file.size is not None and file.size > self.limit:
            raise ValidationError(
                _("File size must be under %(limit)s MB. Current size: %(size)s MB.")
                % {"limit": self.limit // (1024 * 1024), "size": round(file.size / (1024 * 1024), 2)},
                code="file_too_large",
            )

    def __eq__(self, other: object) -> bool:
        if isinstance(other, MaxFileSizeValidator):
            return self.limit == other.limit
        return False

    def __hash__(self) -> int:
        return hash(self.limit)


@deconstructible
class ImageFileValidator:
    """Validates that an uploaded file is a valid image of an allowed type and size."""

    allowed_extensions: set[str]
    allowed_mimes: set[str]
    max_size: int
    size_validator: MaxFileSizeValidator

    def __init__(self, max_size_mb: int = 5) -> None:
        self.allowed_extensions = ALLOWED_IMAGE_EXTENSIONS
        self.allowed_mimes = ALLOWED_IMAGE_MIMES
        self.max_size = max_size_mb * 1024 * 1024
        self.size_validator = MaxFileSizeValidator(max_size_mb)

    def __call__(self, value: object) -> None:
        if hasattr(value, "content_type") and value.content_type not in self.allowed_mimes:
            raise ValidationError(
                _("Invalid file type. Allowed: %(types)s.")
                % {"types": ", ".join(sorted(self.allowed_mimes))},
                code="invalid_image_type",
            )

        if hasattr(value, "name") and value.name is not None:
            ext = value.name.lower()
            if not any(ext.endswith(e) for e in self.allowed_extensions):
                raise ValidationError(
                    _("Invalid file extension. Allowed: %(exts)s.")
                    % {"exts": ", ".join(sorted(self.allowed_extensions))},
                    code="invalid_image_extension",
                )

        if hasattr(value, "read") and callable(value.read):
            original_pos = value.tell()
            content = value.read(32)
            value.seek(original_pos)
            if content:
                try:
                    validate_image_magic(content)
                except ValidationError as exc:
                    raise ValidationError(
                        _("File content does not match an allowed image type."),
                        code="invalid_image_content",
                    ) from exc

        self.size_validator(value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ImageFileValidator):
            return self.max_size == other.max_size
        return False

    def __hash__(self) -> int:
        return hash(self.max_size)

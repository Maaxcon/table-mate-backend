from __future__ import annotations

import io
from typing import Any

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpRequest
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from common.api.exception_handler import custom_exception_handler
from common.validators import ImageFileValidator, MaxFileSizeValidator, validate_image_magic

# ── Helpers ──────────────────────────────────────────────────────────────────


def _valid_jpeg_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="red").save(buf, format="JPEG")
    return buf.getvalue()


def _valid_png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="blue").save(buf, format="PNG")
    return buf.getvalue()


def _valid_gif_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="green").save(buf, format="GIF")
    return buf.getvalue()


def _valid_webp_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="yellow").save(buf, format="WEBP")
    return buf.getvalue()


def _make_file(content: bytes, *, name: str = "test.jpg", content_type: str = "image/jpeg") -> SimpleUploadedFile:
    return SimpleUploadedFile(name=name, content=content, content_type=content_type)


# ── validate_image_magic ─────────────────────────────────────────────────────


class TestValidateImageMagic:
    def test_valid_jpeg(self) -> None:
        validate_image_magic(_valid_jpeg_bytes()[:32])
        # must not raise

    def test_valid_png(self) -> None:
        validate_image_magic(_valid_png_bytes()[:32])

    def test_valid_gif(self) -> None:
        validate_image_magic(_valid_gif_bytes()[:32])

    def test_valid_webp(self) -> None:
        validate_image_magic(_valid_webp_bytes()[:32])

    def test_empty_bytes_raises(self) -> None:
        with pytest.raises(DjangoValidationError, match="Empty file"):
            validate_image_magic(b"")

    def test_invalid_magic_raises(self) -> None:
        with pytest.raises(DjangoValidationError, match="Invalid image type"):
            validate_image_magic(b"this is not an image file")


# ── ImageFileValidator ───────────────────────────────────────────────────────


class TestImageFileValidator:
    def test_valid_jpeg(self) -> None:
        ImageFileValidator()(_make_file(_valid_jpeg_bytes()))
        # must not raise

    def test_valid_png(self) -> None:
        ImageFileValidator()(_make_file(_valid_png_bytes(), name="test.png", content_type="image/png"))

    def test_valid_gif(self) -> None:
        ImageFileValidator()(_make_file(_valid_gif_bytes(), name="test.gif", content_type="image/gif"))

    def test_valid_webp(self) -> None:
        ImageFileValidator()(_make_file(_valid_webp_bytes(), name="test.webp", content_type="image/webp"))

    def test_empty_file(self) -> None:
        with pytest.raises(DjangoValidationError, match="Empty file"):
            ImageFileValidator()(_make_file(b""))

    def test_wrong_content_type(self) -> None:
        with pytest.raises(DjangoValidationError, match="Invalid file type"):
            ImageFileValidator()(_make_file(_valid_jpeg_bytes(), content_type="text/plain"))

    def test_wrong_extension(self) -> None:
        with pytest.raises(DjangoValidationError, match="Invalid file extension"):
            ImageFileValidator()(_make_file(_valid_jpeg_bytes(), name="test.txt"))

    def test_invalid_magic_bytes(self) -> None:
        with pytest.raises(DjangoValidationError, match="does not match an allowed image type"):
            ImageFileValidator()(_make_file(b"not an image" * 100, content_type="image/jpeg"))

    def test_file_too_large(self) -> None:
        content = _valid_jpeg_bytes() + b"\x00" * (6 * 1024 * 1024)
        file = _make_file(content, content_type="image/jpeg")
        with pytest.raises(DjangoValidationError, match="File size must be under"):
            ImageFileValidator(max_size_mb=5)(file)

    def test_image_exceeds_max_dimensions(self) -> None:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (3000, 200), color="red").save(buf, format="JPEG")
        file = _make_file(buf.getvalue())
        with pytest.raises(DjangoValidationError, match="Image dimensions"):
            ImageFileValidator()(file)

    def test_image_within_dimensions(self) -> None:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (500, 500), color="red").save(buf, format="JPEG")
        ImageFileValidator()(_make_file(buf.getvalue()))
        # must not raise

    def test_corrupt_image_after_valid_magic(self) -> None:
        content = b"\xff\xd8\xff" + b"garbage" * 1000
        file = _make_file(content, content_type="image/jpeg")
        with pytest.raises(DjangoValidationError, match="could not be decoded"):
            ImageFileValidator()(file)

    def test_no_read_attr_passes_through(self) -> None:
        ImageFileValidator()("not-a-file-object")

    def test_disabled_dimensions_check(self) -> None:
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (5000, 5000), color="red").save(buf, format="JPEG")
        ImageFileValidator(max_dimensions=None)(_make_file(buf.getvalue()))
        # must not raise


# ── MaxFileSizeValidator ─────────────────────────────────────────────────────


class TestMaxFileSizeValidator:
    def test_under_limit(self) -> None:
        MaxFileSizeValidator(max_size_mb=5)(_make_file(b"x" * 1024))
        # must not raise

    def test_over_limit(self) -> None:
        with pytest.raises(DjangoValidationError, match="File size must be under"):
            MaxFileSizeValidator(max_size_mb=5)(_make_file(b"x" * (6 * 1024 * 1024)))

    def test_no_size_attr_ignored(self) -> None:
        MaxFileSizeValidator()("no-size-attr")


# ── Exception handler Django ValidationError mapping ─────────────────────────


class _DjangoValidationErrorView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request: Any) -> Response:
        raise DjangoValidationError("Something is wrong.", code="test_error")


class _DjangoValidationErrorWithMessagesView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request: Any) -> Response:
        raise DjangoValidationError(["First error.", "Second error."], code="multi_error")


class TestExceptionHandlerDjangoValidationError:
    def test_django_validation_error_returns_400(self) -> None:
        view = _DjangoValidationErrorView.as_view()
        request = APIRequestFactory().get("/")
        response = view(request)
        assert response.status_code == 400
        assert response.data == {
            "detail": "Something is wrong.",
            "code": "test_error",
        }

    def test_django_validation_error_with_multiple_messages(self) -> None:
        view = _DjangoValidationErrorWithMessagesView.as_view()
        request = APIRequestFactory().get("/")
        response = view(request)
        assert response.status_code == 400
        assert response.data["detail"] == "First error."
        assert response.data["code"] == "validation_error"

    def test_handler_delegates_for_non_django_validation_error(self) -> None:
        context: dict[str, object] = {"view": None, "args": (), "kwargs": {}, "request": HttpRequest()}
        result = custom_exception_handler(PermissionDenied("not allowed"), context)
        assert result is not None
        assert result.status_code == 403

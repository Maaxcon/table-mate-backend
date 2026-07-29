from typing import Any

from django.db.models import Model
from django.db.models.query import QuerySet

from ..models import (
    MenuCategoryTranslation,
    MenuItemTranslation,
    MenuTranslation,
)

_TRANSLATION_MODEL_MAP: dict[type[Model], type[Model]] = {}


def _register(model_class: type[Model], translation_class: type[Model]) -> None:
    _TRANSLATION_MODEL_MAP[model_class] = translation_class


from apps.restaurants.models import Restaurant, RestaurantTranslation  # noqa: E402

from ..models import Menu, MenuCategory, MenuItem  # noqa: E402

_register(Menu, MenuTranslation)
_register(MenuCategory, MenuCategoryTranslation)
_register(MenuItem, MenuItemTranslation)
_register(Restaurant, RestaurantTranslation)


def get_translation_model(entity_class: type[Model]) -> type[Model] | None:
    return _TRANSLATION_MODEL_MAP.get(entity_class)


def get_localized_content(entity: Model, language_code: str) -> dict[str, Any]:
    """Return a dict of translated fields for an entity, falling back to
    default entity field values per-field when no translation exists."""
    translation_model = get_translation_model(type(entity))
    if translation_model is None:
        return {}

    translated_fields = _get_translated_fields(translation_model)
    try:
        translation = translation_model.objects.get(  # type: ignore[attr-defined]
            **{_get_fk_name(translation_model): entity.pk},
            language_code=language_code,
        )
        return {field: getattr(translation, field) for field in translated_fields if hasattr(translation, field)}
    except translation_model.DoesNotExist:  # type: ignore[attr-defined]
        return {field: getattr(entity, field, None) for field in translated_fields}


def _get_translated_fields(translation_model: type[Model]) -> list[str]:
    """Identify content fields on a translation model (exclude FK, lang, timestamps)."""
    skip = {"id", "language_code", "created_at", "updated_at"}
    fk_name = _get_fk_name(translation_model)
    skip.add(fk_name)
    return [
        f.name
        for f in translation_model._meta.get_fields()
        if hasattr(f, "name") and f.name not in skip and not f.one_to_many and not f.many_to_many
    ]


def _get_fk_name(translation_model: type[Model]) -> str:
    """Return the FK field name pointing to the parent entity."""
    for field in translation_model._meta.get_fields():
        if getattr(field, "one_to_one", False) or (hasattr(field, "many_to_one") and field.many_to_one):
            return field.name
    return ""


def localize_queryset(
    queryset: QuerySet[Model],
    translation_model: type[Model],
    language_code: str,
) -> list[dict[str, Any]]:
    """Prefetch translations for a queryset and attach localized content.

    Returns the list of dicts with both original fields and localized content.
    """
    if not queryset:
        return []

    fk_name = _get_fk_name(translation_model)
    translated_fields = _get_translated_fields(translation_model)

    translations_map: dict[int, Model] = {}
    for t in translation_model.objects.filter(  # type: ignore[attr-defined]
        **{fk_name + "__in": [obj.pk for obj in queryset]},
        language_code=language_code,
    ):
        parent_pk = getattr(t, fk_name + "_id") if hasattr(t, fk_name + "_id") else getattr(t, fk_name).pk
        translations_map[parent_pk] = t

    results: list[dict[str, Any]] = []
    for obj in queryset:
        data: dict[str, Any] = {}
        base = getattr(obj, "__dict__", {})
        for field in translated_fields:
            if obj.pk in translations_map:
                data[field] = getattr(translations_map[obj.pk], field)
            else:
                data[field] = base.get(field) or getattr(obj, field, None)
        results.append(data)

    return results

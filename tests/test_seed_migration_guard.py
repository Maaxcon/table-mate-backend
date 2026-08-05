# mypy: disable-error-code="no-untyped-call"
from typing import Any

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import QuerySet

from apps.editor.models import LayoutDraft, LayoutVersion
from apps.menu.models import Allergen, Ingredient, Menu
from apps.restaurants.models import Restaurant, RestaurantSettings, Table

_RESTAURANT_NAMES: list[str] = [
    "UniTable",
    "Table Mate Terrace",
    "Смак Дому",
    "Барва",
    "Козацький Двір",
    "Море Смаку",
    "Вогнище",
]

_NEW_RESTAURANT_NAMES: list[str] = [
    "Смак Дому",
    "Барва",
    "Козацький Двір",
    "Море Смаку",
    "Вогнище",
]

_BEFORE_SEEDS = [("restaurants", "0029_tabletranslation_zonetranslation")]
_AFTER_SEEDS = [("restaurants", "0031_seed_new_restaurants")]


def _migrate(targets: list[tuple[str, str]]) -> None:
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)


def _apply_seeds() -> None:
    _migrate(_AFTER_SEEDS)


def _rollback_before_seeds() -> None:
    _migrate(_BEFORE_SEEDS)


def _delete_restaurants(queryset: QuerySet[Restaurant]) -> None:
    # Delete in PROTECT-safe order: LayoutVersion.restaurant, Table.zone,
    # Menu.restaurant, MenuItem.restaurant and Ingredient.restaurant use
    # on_delete=PROTECT, so referenced rows must go before their restaurants.
    LayoutDraft.objects.all().delete()
    LayoutVersion.objects.all().delete()
    Table.objects.all().delete()
    Menu.objects.all().delete()
    Ingredient.objects.all().delete()
    Allergen.objects.all().delete()
    queryset.delete()


def _purge_restaurants() -> None:
    _delete_restaurants(Restaurant.objects.all())


def _seed_existing_db() -> None:
    # Get the DB into an "existing seeded data, seed migrations not yet
    # applied" state: seed via 0030/0031 once, then roll them back (their
    # reverse is a no-op, so the data persists). Mirrors a DB that was seeded
    # by the original 0022/0023 and is now upgrading past the seeds.
    _rollback_before_seeds()
    _apply_seeds()
    _rollback_before_seeds()


def _sentinel_working_hours() -> dict[str, Any]:
    return {"mon": {"open": "07:00", "close": "21:00"}}


def _set_working_hours(name: str) -> RestaurantSettings:
    settings = RestaurantSettings.objects.get(restaurant__name=name)
    settings.working_hours = _sentinel_working_hours()
    settings.save(update_fields=["working_hours"])
    return settings


@pytest.mark.django_db(transaction=True)
def test_fresh_database_seeds_all_restaurants() -> None:
    _rollback_before_seeds()
    _purge_restaurants()
    assert Restaurant.objects.count() == 0

    _apply_seeds()

    names = set(Restaurant.objects.values_list("name", flat=True))
    assert set(_RESTAURANT_NAMES) <= names


@pytest.mark.django_db(transaction=True)
def test_existing_seed_is_not_reseeded() -> None:
    # A DB that already has the seed data must be left alone when the seed
    # migrations apply on top of it.
    _seed_existing_db()

    settings = _set_working_hours("UniTable")
    layout_versions_before = LayoutVersion.objects.count()

    _apply_seeds()

    settings.refresh_from_db()
    assert settings.working_hours == _sentinel_working_hours()
    assert Restaurant.objects.filter(name="UniTable").count() == 1
    assert LayoutVersion.objects.count() == layout_versions_before


@pytest.mark.django_db(transaction=True)
def test_new_restaurants_seed_skipped_when_any_already_exist() -> None:
    _seed_existing_db()

    settings = _set_working_hours("Смак Дому")
    _delete_restaurants(Restaurant.objects.filter(name__in=_NEW_RESTAURANT_NAMES).exclude(name="Смак Дому"))

    _apply_seeds()

    settings.refresh_from_db()
    assert settings.working_hours == _sentinel_working_hours()
    assert Restaurant.objects.filter(name="Смак Дому").count() == 1
    assert not Restaurant.objects.filter(name="Барва").exists()

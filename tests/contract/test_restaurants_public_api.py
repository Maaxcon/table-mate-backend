from typing import Any

import pytest
from django.test import Client
from django.urls import reverse
from rest_framework import status

from apps.restaurants.models import Restaurant, RestaurantSettings


@pytest.mark.django_db(databases=["default"])
class TestPublicRestaurantRetrieve:
    def test_returns_public_restaurant_with_settings_metrics(
        self,
        api_client: Client,
        restaurant: Restaurant,
        restaurant_settings: RestaurantSettings,
    ) -> None:
        url = reverse("restaurant-public-detail", kwargs={"public_id": str(restaurant.public_id)})
        response: Any = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["public_id"] == str(restaurant.public_id)
        assert data["name"] == restaurant.name
        assert data["settings"]["currency"] == "UAH"
        assert data["settings"]["timezone"] == "Europe/Kyiv"
        assert data["settings"]["rating"] == "4.80"
        assert data["settings"]["eta_min_minutes"] == 20
        assert data["settings"]["eta_max_minutes"] == 30
        assert data["settings"]["price_band"] == 2
        assert "working_hours" in data["settings"]

    def test_returns_settings_null_when_no_settings_row(
        self,
        api_client: Client,
        restaurant: Restaurant,
    ) -> None:
        url = reverse("restaurant-public-detail", kwargs={"public_id": str(restaurant.public_id)})
        response: Any = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["settings"] is None

    def test_returns_404_for_missing_public_id(self, api_client: Client) -> None:
        url = reverse("restaurant-public-detail", kwargs={"public_id": "00000000-0000-0000-0000-000000000001"})
        response: Any = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

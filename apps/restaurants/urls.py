from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import RestaurantSettingsViewSet, RestaurantViewSet, TableViewSet

router = DefaultRouter()
router.register("restaurants", RestaurantViewSet, basename="restaurant")
router.register("restaurant-settings", RestaurantSettingsViewSet, basename="restaurant-settings")
router.register("tables", TableViewSet, basename="table")

urlpatterns = [
    path("", include(router.urls)),
]

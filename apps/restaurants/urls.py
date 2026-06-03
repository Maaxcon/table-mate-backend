from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EmployeeViewSet,
    PublicRestaurantViewSet,
    RestaurantSettingsViewSet,
    RestaurantViewSet,
    TableViewSet,
    ZoneViewSet,
)

router = DefaultRouter()
router.register("restaurants", RestaurantViewSet, basename="restaurant")
router.register("restaurant-settings", RestaurantSettingsViewSet, basename="restaurant-settings")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("tables", TableViewSet, basename="table")
router.register("zones", ZoneViewSet, basename="zone")
router.register("restaurants-public", PublicRestaurantViewSet, basename="restaurant-public")

urlpatterns = [
    path("", include(router.urls)),
]

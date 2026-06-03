from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminMenuViewSet,
    MenuCategoryViewSet,
    MenuItemViewSet,
    MenuViewSet,
)

router = DefaultRouter()
router.register("menus", MenuViewSet, basename="menu")
router.register("categories", MenuCategoryViewSet, basename="menu-category")
router.register("items", MenuItemViewSet, basename="menu-item")
router.register("admin/menus", AdminMenuViewSet, basename="admin-menu")

urlpatterns = [
    path("", include(router.urls)),
]

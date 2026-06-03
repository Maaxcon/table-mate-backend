from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminMenuCategoryViewSet,
    AdminMenuItemViewSet,
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
router.register("admin/categories", AdminMenuCategoryViewSet, basename="admin-menu-category")
router.register("admin/items", AdminMenuItemViewSet, basename="admin-menu-item")

urlpatterns = [
    path("", include(router.urls)),
]

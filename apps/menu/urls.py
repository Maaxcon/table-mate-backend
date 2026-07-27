from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminAllergenViewSet,
    AdminMenuCategoryViewSet,
    AdminMenuItemViewSet,
    AdminMenuViewSet,
    AllergenListView,
    MenuCategoryViewSet,
    MenuItemViewSet,
    MenuViewSet,
)

router = DefaultRouter()
router.register("menus", MenuViewSet, basename="menu")
router.register("categories", MenuCategoryViewSet, basename="menu-category")
router.register("items", MenuItemViewSet, basename="menu-item")
router.register("admin/menus", AdminMenuViewSet, basename="admin-menu")
router.register("admin/allergens", AdminAllergenViewSet, basename="admin-allergen")
router.register("admin/categories", AdminMenuCategoryViewSet, basename="admin-menu-category")
router.register("admin/items", AdminMenuItemViewSet, basename="admin-menu-item")

urlpatterns = [
    path("allergens/", AllergenListView.as_view(), name="allergens"),
    path("", include(router.urls)),
]

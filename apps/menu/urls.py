from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdminAllergenViewSet,
    AdminIngredientViewSet,
    AdminMenuCategoryViewSet,
    AdminMenuItemViewSet,
    AdminMenuViewSet,
    AllergenListView,
    IngredientListView,
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
router.register("admin/allergens", AdminAllergenViewSet, basename="admin-allergen")
router.register("admin/ingredients", AdminIngredientViewSet, basename="admin-ingredient")

urlpatterns = [
    path("allergens/", AllergenListView.as_view(), name="allergens"),
    path("ingredients/", IngredientListView.as_view(), name="ingredients"),
    path("", include(router.urls)),
]

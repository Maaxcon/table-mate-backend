from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MenuCategoryViewSet, MenuItemViewSet, MenuViewSet

router = DefaultRouter()
router.register("menus", MenuViewSet, basename="menu")
router.register("menu-categories", MenuCategoryViewSet, basename="menu-category")
router.register("menu-items", MenuItemViewSet, basename="menu-item")

urlpatterns = [
    path("", include(router.urls)),
]

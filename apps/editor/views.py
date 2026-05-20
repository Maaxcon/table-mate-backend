from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import RestaurantScopedViewSetMixin

from .models import Layout
from .serializers import LayoutSerializer


@extend_schema(tags=["Editor"])
class LayoutViewSet(
    RestaurantScopedViewSetMixin[Layout], viewsets.ReadOnlyModelViewSet[Layout]
):
    queryset = Layout.objects.all()
    serializer_class = LayoutSerializer

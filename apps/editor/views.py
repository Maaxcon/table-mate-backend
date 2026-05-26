from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from apps.authentication.permissions import IsFloor
from common.api import RestaurantScopedViewSetMixin

from .models import Layout
from .serializers import LayoutSerializer


@extend_schema(tags=["Editor"])
class LayoutViewSet(RestaurantScopedViewSetMixin[Layout], viewsets.ReadOnlyModelViewSet[Layout]):
    permission_classes = [IsFloor]
    queryset = Layout.objects.all()
    serializer_class = LayoutSerializer
    filterset_fields = ["version", "published_at", "published_by"]
    ordering_fields = ["created_at", "updated_at", "version", "published_at"]

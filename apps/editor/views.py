from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import PublicLookupMixin

from .models import Layout
from .serializers import LayoutSerializer


@extend_schema(tags=["Editor"])
class LayoutViewSet(PublicLookupMixin, viewsets.ReadOnlyModelViewSet[Layout]):
    queryset = Layout.objects.all()
    serializer_class = LayoutSerializer

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from common.api import PublicLookupMixin

from .models import User
from .serializers import UserSerializer


@extend_schema(tags=["Authentication"])
class UserViewSet(PublicLookupMixin, viewsets.ReadOnlyModelViewSet[User]):
    queryset = User.objects.all()
    serializer_class = UserSerializer

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from .models import User
from .serializers import UserSerializer


@extend_schema(tags=["Authentication"])
class UserViewSet(viewsets.ReadOnlyModelViewSet[User]):
    queryset = User.objects.all()
    serializer_class = UserSerializer

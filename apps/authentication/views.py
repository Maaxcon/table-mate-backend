from rest_framework import generics
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User
from .serializers import CustomTokenObtainPairSerializer, UserSerializer


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class MeView(generics.RetrieveAPIView[User]):
    serializer_class = UserSerializer

    def get_object(self) -> User:
        return self.request.user  # type: ignore[return-value]


__all__ = ["CustomTokenObtainPairView", "MeView"]

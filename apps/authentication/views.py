from rest_framework import generics
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import CustomTokenObtainPairSerializer, UserSerializer


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class MeView(generics.RetrieveAPIView):  # type: ignore[type-arg]
    serializer_class = UserSerializer

    def get_object(self) -> object:
        return self.request.user


__all__ = ["CustomTokenObtainPairView", "MeView"]

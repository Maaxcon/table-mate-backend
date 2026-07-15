from rest_framework_simplejwt.tokens import AccessToken, RefreshToken


class CartAwareRefreshToken(RefreshToken):
    @property
    def access_token(self) -> AccessToken:
        access = super().access_token
        if "cart_session_id" in self.payload:
            access["cart_session_id"] = self.payload["cart_session_id"]
        return access

from rest_framework_simplejwt.tokens import RefreshToken


class CartAwareRefreshToken(RefreshToken):
    def generate_access_token(self) -> RefreshToken:
        access = super().generate_access_token()
        if "cart_session_id" in self.payload:
            access["cart_session_id"] = self.payload["cart_session_id"]
        return access

# mypy: disable-error-code=no-untyped-call

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class TokenVersionJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.authentication.authentication.TokenVersionJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema: object) -> dict[str, str]:
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }


class GuestJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.authentication.authentication.GuestJWTAuthentication"
    name = "guestJwtAuth"
    match_subclasses = True

    def get_security_definition(self, auto_schema: object) -> dict[str, str]:
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }

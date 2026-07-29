from typing import Any

from django.utils.deprecation import MiddlewareMixin

from apps.restaurants.models import RestaurantSettings

from .language import parse_accept_language_header, resolve_restaurant_language, select_best_match

STAFF_ROLES = frozenset({"waiter", "cook", "admin"})


class LanguageMiddleware(MiddlewareMixin):
    """Resolve active language for each request.

    Staff-authenticated requests (waiter, cook, admin) always use the
    restaurant's configured locale. Customer/unauthenticated requests use
    the Accept-Language header matched against the restaurant's supported
    languages.
    """

    def process_request(self, request: Any) -> None:
        request.active_language = None
        request.active_language_is_fallback = False

        user = getattr(request, "user", None)
        restaurant = getattr(request, "restaurant", None)

        if restaurant is None and hasattr(request, "auth") and getattr(request.auth, "restaurant_id", None):
            from django.apps import apps
            Restaurant = apps.get_model("restaurants", "Restaurant")
            try:
                restaurant = Restaurant.objects.get(pk=request.auth.restaurant_id)
            except Restaurant.DoesNotExist:
                restaurant = None

        if restaurant is None:
            restaurant_uuid = request.GET.get("restaurant")
            if restaurant_uuid:
                from django.apps import apps
                Restaurant = apps.get_model("restaurants", "Restaurant")
                try:
                    restaurant = Restaurant.objects.get(public_id=restaurant_uuid)
                except Restaurant.DoesNotExist:
                    pass

        if user is not None and user.is_authenticated and getattr(user, "role", None) in STAFF_ROLES:
            rest = restaurant or getattr(user, "restaurant", None)
            if rest is not None:
                try:
                    settings = rest.settings
                except RestaurantSettings.DoesNotExist:
                    settings = None
                if settings:
                    request.active_language = settings.locale
                    request.active_language_is_fallback = False
            return

        rest = restaurant
        if rest is None:
            return

        try:
            settings = rest.settings
        except RestaurantSettings.DoesNotExist:
            return

        locale = settings.locale
        request.active_language = resolve_restaurant_language(
            rest,
            request.META.get("HTTP_ACCEPT_LANGUAGE", ""),
            default=locale,
        )
        request.active_language_is_fallback = (request.active_language != locale)

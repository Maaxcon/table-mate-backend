from rest_framework.throttling import ScopedRateThrottle


class GuestAwareScopedRateThrottle(ScopedRateThrottle):
    def get_cache_key(self, request, view):
        cache_key = super().get_cache_key(request, view)
        if cache_key is None:
            return None

        auth = getattr(request, "auth", None)
        if auth is not None:
            payload = getattr(auth, "payload", {})
            if payload.get("is_guest"):
                guest_id = payload.get("guest_id")
                if guest_id:
                    return self.cache_format % {
                        "scope": self.scope,
                        "ident": f"guest_{guest_id}",
                    }

        return cache_key


__all__ = [
    "GuestAwareScopedRateThrottle",
]

from typing import Any

from rest_framework.filters import OrderingFilter


class StableOrderingFilter(OrderingFilter):
        
    def filter_queryset(self, request: Any, queryset: Any, view: Any) -> Any:
        ordering = self.get_ordering(request, queryset, view)
        if ordering:
            ordering = list(ordering)
            if not any(field.lstrip("-") in {"pk", "id"} for field in ordering):
                ordering.append("pk")
            return queryset.order_by(*ordering)
        return queryset

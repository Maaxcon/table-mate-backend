import django_filters
from django.db.models import QuerySet

from .models import Reservation


class ReservationFilter(django_filters.FilterSet):  # type: ignore[misc]
    status__in = django_filters.CharFilter(method="filter_status_in")
    start_at__date__gte = django_filters.DateFilter(
        field_name="start_at", lookup_expr="date__gte",
    )
    start_at__date__lte = django_filters.DateFilter(
        field_name="start_at", lookup_expr="date__lte",
    )

    class Meta:
        model = Reservation
        fields = ["customer", "table", "status"]

    def filter_status_in(self, queryset: QuerySet[Reservation], name: str, value: str) -> QuerySet[Reservation]:
        statuses = value.split(",")
        return queryset.filter(**{f"{name}": statuses})

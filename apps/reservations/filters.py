import django_filters
from django.db.models import QuerySet

from .models import Reservation


class ReservationFilter(django_filters.FilterSet):  # type: ignore[misc]
    status__in = django_filters.CharFilter(method="filter_status_in")

    class Meta:
        model = Reservation
        fields = ["customer", "table", "status"]

    def filter_status_in(self, queryset: QuerySet[Reservation], name: str, value: str) -> QuerySet[Reservation]:
        statuses = value.split(",")
        return queryset.filter(**{f"{name}": statuses})

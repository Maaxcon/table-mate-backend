from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Receipt
from .serializers import ReceiptSerializer


@extend_schema(tags=["Receipts"])
class MyReceiptsView(generics.ListAPIView[Receipt]):
    """The signed-in user's own receipt history, newest first."""

    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # a user's history is small; return a plain list

    def get_queryset(self) -> QuerySet[Receipt]:
        return (
            Receipt.objects.filter(customer_id=self.request.user.pk)
            .select_related("restaurant", "order__session__reservation")
            .prefetch_related("items")
        )

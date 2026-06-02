from django.urls import path

from .views import MyReceiptsView

urlpatterns = [
    path("my/", MyReceiptsView.as_view(), name="my-receipts"),
]

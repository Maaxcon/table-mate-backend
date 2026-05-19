from django.db import models

from common.mixins import TimestampMixin, UUIDMixin


class BaseModel(UUIDMixin, TimestampMixin):
    class Meta:
        abstract = True


class RestaurantScopedModel(BaseModel):
    restaurant = models.ForeignKey("restaurants.Restaurant", on_delete=models.PROTECT)

    class Meta:
        abstract = True

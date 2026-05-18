import uuid

from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PublicIdentifierModel(models.Model):
    public_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False, db_index=True
    )

    class Meta:
        abstract = True


class BaseModel(PublicIdentifierModel, TimestampedModel):
    class Meta:
        abstract = True


class RestaurantScopedModel(BaseModel):
    restaurant = models.ForeignKey("restaurants.Restaurant", on_delete=models.PROTECT)

    class Meta:
        abstract = True

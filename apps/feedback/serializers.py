from rest_framework import serializers

from apps.authentication.models import User
from apps.menu.models import MenuItem
from apps.orders.models import Order
from apps.restaurants.models import Restaurant
from common.api import PublicIdRelatedField

from .models import DishFeedback, Feedback


class DishFeedbackSerializer(serializers.ModelSerializer[DishFeedback]):
    menu_item: PublicIdRelatedField[MenuItem] = PublicIdRelatedField(read_only=True)
    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)

    class Meta:
        model = DishFeedback
        fields = [
            "public_id",
            "menu_item",
            "menu_item_name",
            "rating",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["public_id", "created_at", "updated_at"]


class FeedbackListSerializer(serializers.ModelSerializer[Feedback]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    guest: PublicIdRelatedField[User] = PublicIdRelatedField(read_only=True)
    order: PublicIdRelatedField[Order] = PublicIdRelatedField(read_only=True)
    guest_name = serializers.SerializerMethodField()
    guest_identity = serializers.CharField(read_only=True)

    class Meta:
        model = Feedback
        fields = [
            "public_id",
            "restaurant",
            "guest",
            "guest_name",
            "guest_identity",
            "order",
            "overall_rating",
            "service_rating",
            "comment",
            "review_status",
            "prompt_shown_at",
            "dismissed",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "public_id",
            "restaurant",
            "guest",
            "guest_name",
            "guest_identity",
            "order",
            "overall_rating",
            "service_rating",
            "comment",
            "prompt_shown_at",
            "dismissed",
            "created_at",
            "updated_at",
        ]

    def get_guest_name(self, obj: Feedback) -> str:
        if obj.guest:
            return obj.guest.get_full_name()
        return "Guest"


class FeedbackDetailSerializer(FeedbackListSerializer):
    dish_feedback = DishFeedbackSerializer(many=True, read_only=True)

    class Meta(FeedbackListSerializer.Meta):
        fields = FeedbackListSerializer.Meta.fields + ["dish_feedback"]


class DishFeedbackInputSerializer(serializers.Serializer[dict[str, object]]):
    menu_item = serializers.UUIDField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class GuestFeedbackCreateSerializer(serializers.Serializer[dict[str, object]]):
    order = serializers.UUIDField()
    overall_rating = serializers.IntegerField(min_value=1, max_value=5)
    service_rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default="")
    dish_feedback = DishFeedbackInputSerializer(many=True, required=False)

    class Meta:
        fields = [
            "order",
            "overall_rating",
            "service_rating",
            "comment",
            "dish_feedback",
        ]


class GuestFeedbackListSerializer(serializers.ModelSerializer[Feedback]):
    restaurant: PublicIdRelatedField[Restaurant] = PublicIdRelatedField(read_only=True)
    order: PublicIdRelatedField[Order] = PublicIdRelatedField(read_only=True)
    dish_feedback = DishFeedbackSerializer(many=True, read_only=True)

    class Meta:
        model = Feedback
        fields = [
            "public_id",
            "restaurant",
            "order",
            "overall_rating",
            "service_rating",
            "comment",
            "created_at",
            "updated_at",
            "dish_feedback",
        ]
        read_only_fields = [
            "public_id",
            "restaurant",
            "order",
            "overall_rating",
            "service_rating",
            "comment",
            "created_at",
            "updated_at",
            "dish_feedback",
        ]

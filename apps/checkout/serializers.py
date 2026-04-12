from decimal import Decimal
from rest_framework import serializers
from apps.food_menus.models import ModifierOption
from .models import Cart, CartItem, CustomerCar, Order, OrderItem, OrderRating


# --- Cart Serializers ---------------------------------------------------------

class AddToCartSerializer(serializers.Serializer):
    branch_id = serializers.UUIDField()
    menu_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    selected_options = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class ClearCartSerializer(serializers.Serializer):
    branch_id = serializers.UUIDField()


class SelectedOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    group_name = serializers.CharField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=8, decimal_places=2)


class CartItemSerializer(serializers.ModelSerializer):
    cart_item_id     = serializers.UUIDField(source="id")
    menu_item_id     = serializers.UUIDField(source="menu_item.id")
    name             = serializers.CharField(source="menu_item.name")
    subtotal         = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    selected_options = serializers.SerializerMethodField()

    class Meta:
        model  = CartItem
        fields = [
            "cart_item_id", "menu_item_id", "name",
            "quantity", "item_price", "options_price",
            "subtotal", "selected_options",
        ]

    def get_selected_options(self, obj):
        options = []
        for opt_id in obj.selected_options:
            try:
                opt = ModifierOption.objects.select_related("group").get(id=opt_id)
                options.append({
                    "id":         str(opt.id),
                    "group_name": opt.group.name,
                    "name":       opt.name,
                    "price":      str(opt.price),
                })
            except ModifierOption.DoesNotExist:
                pass
        return options


class CartSerializer(serializers.ModelSerializer):
    cart_id         = serializers.UUIDField(source="id")
    branch_id       = serializers.UUIDField(source="branch.id")
    branch_name     = serializers.CharField(source="branch.name")
    restaurant_name = serializers.CharField(source="branch.restaurant.brand_name")
    items           = CartItemSerializer(many=True, read_only=True)
    total           = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model  = Cart
        fields = [
            "cart_id", "branch_id", "branch_name",
            "restaurant_name", "items", "total",
        ]


# --- Car Serializers ----------------------------------------------------------

class CustomerCarSerializer(serializers.ModelSerializer):
    class Meta:
        model  = CustomerCar
        fields = ["id", "car_model", "plate_number", "car_color"]
        read_only_fields = ["id"]

    def validate_car_color(self, v):
        if not v.startswith("#") or len(v) not in (4, 7):
            raise serializers.ValidationError("Must be a valid hex color e.g. #FF0000")
        return v.upper()


# --- Order Serializers --------------------------------------------------------

class PlaceOrderSerializer(serializers.Serializer):
    branch_id      = serializers.UUIDField()
    car_id         = serializers.UUIDField()
    note           = serializers.CharField(required=False, allow_blank=True, default="")
    pickup_time    = serializers.CharField(max_length=50)
    payment_method = serializers.ChoiceField(choices=Order.PaymentMethod.choices)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model  = OrderItem
        fields = ["id", "name", "price", "options_price", "quantity", "selected_options", "subtotal"]


class OrderSerializer(serializers.ModelSerializer):
    items       = OrderItemSerializer(many=True, read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    car         = CustomerCarSerializer(read_only=True)
    status_timestamps = serializers.SerializerMethodField()

    class Meta:
        model  = Order
        fields = [
            "id", "order_number", "status", "payment_method", "payment_status",
            "note", "pickup_time",
            "subtotal", "service_fee", "vat", "total",
            "branch_name", "car", "items",
            "status_timestamps", "created_at",
        ]

    def get_status_timestamps(self, obj):
        return {
            "accepted_at":  obj.accepted_at,
            "preparing_at": obj.preparing_at,
            "ready_at":     obj.ready_at,
            "delivered_at": obj.delivered_at,
            "cancelled_at": obj.cancelled_at,
        }


class OrderListSerializer(serializers.ModelSerializer):
    branch_name     = serializers.CharField(source="branch.name", read_only=True)
    restaurant_name = serializers.CharField(source="branch.restaurant.brand_name", read_only=True)
    item_count      = serializers.SerializerMethodField()
    car             = CustomerCarSerializer(read_only=True)

    class Meta:
        model  = Order
        fields = [
            "id", "order_number", "status", "payment_method", "payment_status",
            "total", "pickup_time", "note",
            "branch_name", "restaurant_name",
            "item_count", "car", "created_at",
        ]

    def get_item_count(self, obj):
        return obj.items.count()


class CashConfirmSerializer(serializers.Serializer):
    amount_received = serializers.DecimalField(max_digits=10, decimal_places=2)


class OrderStatusUpdateSerializer(serializers.Serializer):
    prep_time = serializers.IntegerField(
        required=False,
        help_text="Estimated prep time in minutes (required when accepting)"
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Reason for cancellation"
    )


class OrderRatingSerializer(serializers.ModelSerializer):
    class Meta:
        model  = OrderRating
        fields = ["id", "stars", "feedback", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_stars(self, v):
        if not 1 <= v <= 5:
            raise serializers.ValidationError("Stars must be between 1 and 5.")
        return v
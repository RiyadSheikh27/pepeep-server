from decimal import Decimal
from rest_framework import serializers

from apps.food_menus.models import ModifierOption
from .models import Car, Cart, CartItem, Order, OrderItem, Payment, Feedback


# --- CAR ---------------------------------------------------------------------------


class CarSerializer(serializers.ModelSerializer):
    class Meta:
        model = Car
        fields = ["id", "car_model", "plate_number", "color"]
        read_only_fields = ["id"]

    def validate_color(self, v):
        if not v.startswith("#") or len(v) not in (4, 7):
            raise serializers.ValidationError(
                "Must be a valid hex color e.g. #FF0000 or #FFF"
            )
        return v.upper()


# --- CART ---------------------------------------------------------------------------


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


class CartItemSerializer(serializers.ModelSerializer):
    cart_item_id = serializers.UUIDField(source="id")
    menu_item_id = serializers.UUIDField(source="menu_item.id")
    name = serializers.CharField(source="menu_item.name")
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    selected_options = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "cart_item_id",
            "menu_item_id",
            "name",
            "quantity",
            "item_price",
            "options_price",
            "subtotal",
            "selected_options",
        ]

    def get_selected_options(self, obj):
        result = []
        for opt_id in obj.selected_options:
            try:
                opt = ModifierOption.objects.select_related("group").get(id=opt_id)
                result.append(
                    {
                        "id": str(opt.id),
                        "group_name": opt.group.name,
                        "name": opt.name,
                        "price": str(opt.price),
                    }
                )
            except ModifierOption.DoesNotExist:
                pass
        return result


class CartSerializer(serializers.ModelSerializer):
    cart_id = serializers.UUIDField(source="id")
    branch_id = serializers.UUIDField(source="branch.id")
    branch_name = serializers.CharField(source="branch.name")
    restaurant_name = serializers.CharField(source="branch.restaurant.brand_name")
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = [
            "cart_id",
            "branch_id",
            "branch_name",
            "restaurant_name",
            "items",
            "total",
        ]


# --- CHECKOUT — Step 1 (initiate) --------------------------------------------------------------------------------------


class CheckoutInitSerializer(serializers.Serializer):
    """
    User picks branch + payment method to create a Stripe intent
    (or get a cash summary). No order is created yet.
    """

    branch_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(choices=Payment.Method.choices)


# --- CHECKOUT — Step 2 (confirm order) --------------------------------------------------------------------------------------


class ConfirmOrderSerializer(serializers.Serializer):
    """
    Submitted after the user has confirmed payment on the frontend.
    For Stripe: frontend confirms the intent; we verify server-side.
    For cash: no extra fields needed.
    """

    branch_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(choices=[("stripe","Stripe"),("cash","Cash"),("wallet","Wallet")])
    # Required for Stripe flow — the intent id returned from Step 1
    stripe_intent_id = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    pickup_time = serializers.CharField(max_length=50)
    # Inline car — user selects or provides a new car at confirmation
    car_id = serializers.UUIDField(required=False, allow_null=True)
    # OR provide a new car inline (if car_id is null)
    car_model = serializers.CharField(max_length=100, required=False, allow_blank=True)
    plate_number = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    car_color = serializers.CharField(max_length=7, required=False, allow_blank=True)

    def validate(self, attrs):
        method = attrs.get("payment_method")
        if method == Payment.Method.STRIPE and not attrs.get("stripe_intent_id"):
            raise serializers.ValidationError(
                {"stripe_intent_id": "Required for Stripe payment."}
            )
        # Must have either car_id OR the three inline car fields
        has_car_id = bool(attrs.get("car_id"))
        has_inline_car = all(
            [
                attrs.get("car_model"),
                attrs.get("plate_number"),
                attrs.get("car_color"),
            ]
        )
        if not has_car_id and not has_inline_car:
            raise serializers.ValidationError(
                "Provide either car_id or (car_model, plate_number, car_color)."
            )
        return attrs


# --- PAYMENT --------------------------------------------------------------------------------------


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "method",
            "status",
            "amount",
            "stripe_intent_id",
            "cash_received_at",
            "created_at",
        ]
        read_only_fields = fields


class CashReceiveSerializer(serializers.Serializer):
    amount_received = serializers.DecimalField(max_digits=10, decimal_places=2)


# --- ORDER ITEM --------------------------------------------------------------------------------------


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "name",
            "price",
            "options_price",
            "quantity",
            "selected_options",
            "subtotal",
        ]


# --- ORDER  (full detail) --------------------------------------------------------------------------------------


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    payment = PaymentSerializer(read_only=True)
    car = CarSerializer(read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    restaurant_name = serializers.CharField(
        source="branch.restaurant.brand_name", read_only=True
    )
    status_timestamps = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "note",
            "pickup_time",
            "subtotal",
            "service_fee",
            "vat",
            "total",
            "user_arrived",
            "user_arrived_at",
            "branch_name",
            "restaurant_name",
            "car",
            "payment",
            "items",
            "status_timestamps",
            "created_at",
        ]

    def get_status_timestamps(self, obj):
        return {
            "preparing_at": obj.preparing_at,
            "ready_at": obj.ready_at,
            "delivered_at": obj.delivered_at,
            "cancelled_at": obj.cancelled_at,
        }


# --- ORDER  (list — lightweight) --------------------------------------------------------------------------------------


class OrderListSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    restaurant_name = serializers.CharField(
        source="branch.restaurant.brand_name", read_only=True
    )
    payment_method = serializers.CharField(source="payment.method", read_only=True)
    payment_status = serializers.CharField(source="payment.status", read_only=True)
    item_count = serializers.SerializerMethodField()
    car = CarSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "total",
            "pickup_time",
            "branch_name",
            "restaurant_name",
            "payment_method",
            "payment_status",
            "item_count",
            "car",
            "user_arrived",
            "created_at",
        ]

    def get_item_count(self, obj):
        return obj.items.count()


# --- EMPLOYEE — ACCEPT ORDER --------------------------------------------------------------------------------------


class AcceptOrderSerializer(serializers.Serializer):
    prep_time = serializers.IntegerField(
        required=False,
        min_value=1,
        help_text="Estimated preparation time in minutes",
    )


# --- EMPLOYEE — STATUS UPDATE  (PREPARING → READY) --------------------------------------------------------------------------------------


class UpdateStatusSerializer(serializers.Serializer):
    ALLOWED_TRANSITIONS = {
        Order.Status.PREPARING: Order.Status.READY,
    }
    # reason is only for cancellation
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# --- CANCEL ORDER --------------------------------------------------------------------------------------


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# --- MARK ARRIVED  (user) --------------------------------------------------------------------------------------


class MarkArrivedSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )


# --- QR SCAN  (employee) --------------------------------------------------------------------------------------


class QRScanSerializer(serializers.Serializer):
    qr_token = serializers.CharField()


# --- FEEDBACK --------------------------------------------------------------------------------------


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ["id", "stars", "comment", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_stars(self, v):
        if not 1 <= v <= 5:
            raise serializers.ValidationError("Stars must be between 1 and 5.")
        return v


# --- DISTANCE / ETA  (read-only, computed in view) --------------------------------------------------------------------------------------


class OrderETASerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    user_arrived = serializers.BooleanField()
    distance_km = serializers.FloatField(allow_null=True)
    eta_minutes = serializers.FloatField(allow_null=True)
    remaining_minutes = serializers.FloatField(allow_null=True)
    arrived_lat = serializers.DecimalField(
        max_digits=9, decimal_places=6, allow_null=True
    )
    arrived_lon = serializers.DecimalField(
        max_digits=9, decimal_places=6, allow_null=True
    )

from rest_framework import serializers
from .models import (
    CommissionSettings,
    RestaurantCommission,
    OwnerWallet,
    CommissionTransaction,
    PayoutRequest,
    SupportTicket,
)


# --- COMMISSION SETTINGS -------------------------------------------------------------------------------------------------------


class CommissionSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommissionSettings
        fields = ["percentage", "percentage_active", "fixed_sar", "fixed_active"]

    def validate_percentage(self, v):
        if v < 0 or v > 100:
            raise serializers.ValidationError("Percentage must be between 0 and 100.")
        return v

    def validate_fixed_sar(self, v):
        if v < 0:
            raise serializers.ValidationError("Fixed SAR cannot be negative.")
        return v


# --- RESTAURANT COMMISSION (custom rate) -------------------------------------------------------------------------------------------------------


class RestaurantCommissionSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(
        source="restaurant.brand_name", read_only=True
    )
    restaurant_id = serializers.UUIDField(source="restaurant.id", read_only=True)

    class Meta:
        model = RestaurantCommission
        fields = [
            "restaurant_id",
            "restaurant_name",
            "percentage",
            "percentage_active",
            "fixed_sar",
            "fixed_active",
        ]


class CustomRateWriteSerializer(serializers.Serializer):
    restaurant_id = serializers.UUIDField()
    percentage = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False
    )
    percentage_active = serializers.BooleanField(required=False)
    fixed_sar = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    fixed_active = serializers.BooleanField(required=False)

    def validate_percentage(self, v):
        if v < 0 or v > 100:
            raise serializers.ValidationError("Percentage must be between 0 and 100.")
        return v

    def validate_fixed_sar(self, v):
        if v < 0:
            raise serializers.ValidationError("Fixed SAR cannot be negative.")
        return v


class CustomRateListSerializer(serializers.Serializer):
    """Read-only flat representation used in the custom rates list."""

    restaurant_id = serializers.UUIDField()
    restaurant_name = serializers.CharField()
    percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    fixed_sar = serializers.DecimalField(max_digits=8, decimal_places=2)
    is_custom = serializers.BooleanField()


# --- COMMISSION TRANSACTION -------------------------------------------------------------------------------------------------------


class CommissionTransactionSerializer(serializers.ModelSerializer):
    restaurant = serializers.CharField(source="restaurant.brand_name", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)

    class Meta:
        model = CommissionTransaction
        fields = [
            "id",
            "restaurant",
            "order_number",
            "subtotal",
            "commission_amount",
            "status",
            "created_at",
        ]
        read_only_fields = fields


# --- OWNER WALLET -------------------------------------------------------------------------------------------------------


class OwnerWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = OwnerWallet
        fields = ["balance"]
        read_only_fields = fields


# --- PAYOUT REQUEST -------------------------------------------------------------------------------------------------------


class PayoutRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutRequest
        fields = [
            "id",
            "amount",
            "bank_name",
            "account_name",
            "account_number",
            "note",
            "status",
            "rejection_reason",
            "actioned_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "rejection_reason",
            "actioned_at",
            "created_at",
        ]

    def validate_amount(self, v):
        if v <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return v


class PayoutActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["accept", "reject"])
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# --- SUPPORT TICKET -------------------------------------------------------------------------------------------------------


class SupportTicketSerializer(serializers.ModelSerializer):
    order = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "full_name",
            "email",
            "description",
            "order",
            "status",
            "admin_reply",
            "replied_at",
            "created_at",
        ]
        read_only_fields = ["id", "status", "admin_reply", "replied_at", "created_at"]

    def get_order(self, obj):
        return obj.order.order_number if obj.order else None


class SupportTicketCreateSerializer(serializers.Serializer):
    order_id = serializers.UUIDField(required=False, allow_null=True)
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    description = serializers.CharField()


class SupportTicketReplySerializer(serializers.Serializer):
    admin_reply = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=SupportTicket.Status.choices,
        required=False,
    )


# --- DASHBOARD  (read-only response serializers) -------------------------------------------------------------------------------------------------------


class DayTrendSerializer(serializers.Serializer):
    day = serializers.CharField()
    value = serializers.FloatField()


class AdminDashboardSerializer(serializers.Serializer):
    today_orders = serializers.IntegerField()
    order_change_pct = serializers.FloatField()
    today_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_change_pct = serializers.FloatField()
    avg_delivery_minutes = serializers.FloatField(allow_null=True)
    commission_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_trend = DayTrendSerializer(many=True)
    recent_orders = serializers.ListField()


class OwnerDashboardSerializer(serializers.Serializer):
    today_orders = serializers.IntegerField()
    order_change_pct = serializers.FloatField()
    today_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_change_pct = serializers.FloatField()
    active_branches = serializers.IntegerField()
    pending_approvals = serializers.IntegerField()
    total_customers = serializers.IntegerField()
    pending_tickets = serializers.IntegerField()
    order_overview = DayTrendSerializer(many=True)
    revenue_trend = DayTrendSerializer(many=True)


class OwnerWalletStatsSerializer(serializers.Serializer):
    wallet_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    sales_change_pct = serializers.FloatField()
    total_orders = serializers.IntegerField()
    orders_change_pct = serializers.FloatField()
    avg_order_value = serializers.DecimalField(max_digits=10, decimal_places=2)
    avg_order_change_pct = serializers.FloatField()
    revenue_trend = DayTrendSerializer(many=True)
    order_volume = DayTrendSerializer(many=True)

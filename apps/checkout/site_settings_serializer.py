"""
This serializers is for customer wallet, visibility, manager, and fixed admin serializers.
"""

from rest_framework import serializers
from apps.utils.custom_fields import AbsoluteURLImageField, AbsoluteURLFileField
from apps.restaurants.models import Branch, BranchOpeningHours
from .models import (
    CustomerWallet,
    CustomerWalletTransaction,
    VisibilitySettings,
    AdminManager,
)


#  --- CUSTOMER WALLET --------------------------------------------------------------------------


class CustomerWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerWallet
        fields = ["balance"]
        read_only_fields = fields


class CustomerWalletTransactionSerializer(serializers.ModelSerializer):
    actioned_by = serializers.SerializerMethodField()

    class Meta:
        model = CustomerWalletTransaction
        fields = ["id", "tx_type", "amount", "reason", "actioned_by", "created_at"]
        read_only_fields = fields

    def get_actioned_by(self, obj):
        return obj.actioned_by.full_name if obj.actioned_by else "System"


class WalletAdjustmentSerializer(serializers.Serializer):
    """Admin: credit / debit / bonus a customer wallet."""

    tx_type = serializers.ChoiceField(choices=["credit", "debit", "bonus"])
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    reason = serializers.CharField()

    def validate_amount(self, v):
        if v <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return v


#  --- VISIBILITY SETTINGS --------------------------------------------------------------------------


class VisibilitySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisibilitySettings
        fields = ["radius_km"]

    def validate_radius_km(self, v):
        if v <= 0:
            raise serializers.ValidationError("Radius must be greater than 0.")
        return v


#  --- ADMIN MANAGER --------------------------------------------------------------------------


class AdminManagerSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)

    class Meta:
        model = AdminManager
        fields = [
            "id",
            "full_name",
            "email",
            "phone",
            "access_level",
            "is_active",
            "created_at",
        ]
        read_only_fields = fields


class CreateManagerSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=8)
    access_level = serializers.ChoiceField(choices=AdminManager.AccessLevel.choices)


#  --- CHANGE PASSWORD --------------------------------------------------------------------------


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)


class AdminSetPasswordSerializer(serializers.Serializer):
    """Admin/Owner sets password for another user (no old_password needed)."""

    new_password = serializers.CharField(write_only=True, min_length=8)


#  --- FIXED ADMIN — OWNER DETAIL  (with documents + branches) --------------------------------------------------------------------------


class BranchOpeningHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = BranchOpeningHours
        fields = ["day", "is_open", "shifts"]


class BranchDetailAdminSerializer(serializers.ModelSerializer):
    opening_hours = BranchOpeningHoursSerializer(many=True, read_only=True)

    class Meta:
        model = Branch
        fields = [
            "id",
            "name",
            "city",
            "full_address",
            "phone",
            "email",
            "min_order",
            "is_active",
            "latitude",
            "longitude",
            "opening_hours",
        ]


class OwnerDetailAdminSerializer(serializers.Serializer):
    """Full owner detail for admin — fixes missing docs/branches/avatar."""

    id = serializers.UUIDField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.EmailField()
    avatar = AbsoluteURLImageField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()

    # Restaurant info
    restaurant_id = serializers.UUIDField(allow_null=True)
    brand_name = serializers.CharField(allow_null=True)
    legal_name = serializers.CharField(allow_null=True)
    logo = serializers.SerializerMethodField()
    status = serializers.CharField(allow_null=True)
    cr_number = serializers.CharField(allow_null=True)
    vat_number = serializers.CharField(allow_null=True)
    cr_document = serializers.SerializerMethodField()
    vat_certificate = serializers.SerializerMethodField()
    short_description = serializers.CharField(allow_null=True)
    city = serializers.CharField(allow_null=True)
    street_name = serializers.CharField(allow_null=True)

    # Branches
    branches = BranchDetailAdminSerializer(many=True)

    def get_logo(self, obj):
        return _abs(obj.get("logo"))

    def get_cr_document(self, obj):
        return _abs(obj.get("cr_document"))

    def get_vat_certificate(self, obj):
        return _abs(obj.get("vat_certificate"))


def _abs(field_file):
    """Return absolute URL from a FileField/ImageField value."""
    import os
    from django.conf import settings as django_settings

    if not field_file:
        return None
    try:
        url = field_file.url
    except Exception:
        return None
    base = os.getenv("BASE_URL", getattr(django_settings, "BASE_URL", "")).rstrip("/")
    if base and not url.startswith("http"):
        return f"{base}/{url.lstrip('/')}"
    return url


#  --- FIXED ADMIN — CUSTOMER DETAIL  (with wallet + orders)


class CustomerDetailAdminSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    username = serializers.CharField(allow_null=True)
    phone = serializers.CharField(allow_null=True)
    email = serializers.EmailField(allow_null=True)
    avatar = serializers.SerializerMethodField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    total_orders = serializers.IntegerField()
    wallet_balance = serializers.DecimalField(max_digits=12, decimal_places=2)

    def get_avatar(self, obj):
        return _abs(obj.get("avatar"))


class CustomerOrderHistorySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    order_number = serializers.CharField()
    status = serializers.CharField()
    total = serializers.DecimalField(max_digits=10, decimal_places=2)
    created_at = serializers.DateTimeField()

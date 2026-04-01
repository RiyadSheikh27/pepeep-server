from rest_framework import serializers
from .models import Restaurant, RestaurantBankDetail, Branch, BranchOpeningHours


class OpeningHoursReadSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BranchOpeningHours
        fields = ["id", "day", "is_open", "shifts"]


class BranchDetailSerializer(serializers.ModelSerializer):
    opening_hours = OpeningHoursReadSerializer(many=True, read_only=True)

    class Meta:
        model  = Branch
        fields = ["id", "name", "city", "full_address", "min_order", "is_active", "opening_hours"]


class RestaurantBankDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RestaurantBankDetail
        fields = ["bank_name", "account_holder_name", "iban"]


class RestaurantDetailSerializer(serializers.ModelSerializer):
    bank_detail = RestaurantBankDetailSerializer(read_only=True)

    class Meta:
        model  = Restaurant
        fields = [
            "id", "brand_name", "legal_name", "category", "logo", "short_description",
            "cr_number", "vat_number", "cr_document", "vat_certificate",
            "short_address", "street_name", "building_number", "building_secondary_number",
            "district", "postal_code", "unit_number", "city", "country",
            "status", "is_active",
            "bank_detail",
        ]
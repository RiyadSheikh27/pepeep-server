from rest_framework import serializers
from apps.utils.custom_fields import AbsoluteURLImageField, AbsoluteURLFileField
from .models import Restaurant, RestaurantBankDetail, Branch, BranchOpeningHours, RestaurantCategory    

# --- Opening Hours ------------------------------------------------------------------------

class OpeningHoursReadSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BranchOpeningHours
        fields = ["id", "day", "is_open", "shifts"]

"""
GET - BranchDetailSerializer(branch)
PATCH - BranchDetailSerializer(branch, data=request.data, partial=True)
"""
class BranchDetailSerializer(serializers.ModelSerializer):
    opening_hours = OpeningHoursReadSerializer(many=True, read_only=True)

    class Meta:
        model  = Branch
        fields = ["id", "name", "city", "full_address", "min_order", "is_active", "opening_hours"]
        read_only_fields = ["id", "is_active", "opening_hours"]


"""
GET - RestaurantBankDetailSerializer(bank)
PATCH - RestaurantBankDetailSerializer(bank, data=request.data, partial=True)
"""

class RestaurantBankDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RestaurantBankDetail
        fields = ["bank_name", "account_holder_name", "iban", "bank_iban_pdf"]
        extra_kwargs = {
            "bank_iban_pdf": {"write_only": True, "required": False},
        }

    def validate_iban(self, v):
        v = v.replace(" ", "").upper()
        if not v.startswith("SA") or len(v) != 24:
            raise serializers.ValidationError("Must be a valid Saudi IBAN (SA + 22 digits).")
        return v


"""
GET - RestaurantSerializer(restaurant)
PATCH - RestaurantSerializer(restaurant, data=request.data, partial=True)
"""

class RestaurantCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = RestaurantCategory
        fields = ["id", "name", "icon", "banner"]
        read_only_fields = ["id"]

class RestaurantSerializer(serializers.ModelSerializer):
    bank_detail = RestaurantBankDetailSerializer(read_only=True)
    logo = AbsoluteURLImageField(read_only=True)
    cr_document = AbsoluteURLFileField(read_only=True)
    vat_certificate = AbsoluteURLFileField(read_only=True)
    category = RestaurantCategorySerializer(read_only=True, many=False)

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
        read_only_fields = ["id", "status", "is_active", "bank_detail"]


# --- Admin list view -- flat, lightweight -----------------------------------

class RestaurantListSerializer(serializers.ModelSerializer):
    owner_name  = serializers.CharField(source="owner.full_name", read_only=True)
    owner_phone = serializers.CharField(source="owner.phone", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    logo = AbsoluteURLImageField(read_only=True)

    class Meta:
        model  = Restaurant
        fields = [
            "id", "brand_name", "legal_name", "category", "category_name",
            "logo", "city", "status", "is_active",
            "owner_name", "owner_phone", "created_at",
        ]


class BranchListSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.brand_name", read_only=True)

    class Meta:
        model  = Branch
        fields = ["id", "name", "city", "full_address", "min_order", "is_active", "restaurant_name", "created_at"]


# --- Restaurant Category Serializers ---------------------------------------------------------------

class RestaurantCategoryListSerializer(serializers.ModelSerializer):
    icon = AbsoluteURLImageField(read_only=True)
    banner = AbsoluteURLImageField(read_only=True)

    class Meta:
        model = RestaurantCategory
        fields = ["id", "name", "icon", "banner"]
        read_only_fields = ["id"]

class RestaurantCategoryDetailSerializer(serializers.ModelSerializer):
    icon = AbsoluteURLImageField(read_only=True)
    banner = AbsoluteURLImageField(read_only=True)

    class Meta:
        model = RestaurantCategory
        fields = ["id", "name", "icon", "banner", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class RestaurantCategoryWriteSerializer(serializers.ModelSerializer):
    icon = AbsoluteURLImageField(required=False, allow_null=True)
    banner = AbsoluteURLImageField(required=False, allow_null=True)

    class Meta:
        model = RestaurantCategory
        fields = ["name", "icon", "banner"]

    def validate_name(self, value):
        """Check if category name is unique"""
        instance = self.instance
        queryset = RestaurantCategory.objects.filter(name__iexact=value)
        
        if instance:
            queryset = queryset.exclude(pk=instance.pk)
        
        if queryset.exists():
            raise serializers.ValidationError("A category with this name already exists.")
        
        return value


# --- Restaurant Search Serializers ---------------------------------------------------------------

class RestaurantSearchSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_icon = AbsoluteURLImageField(source="category.icon", read_only=True)
    category_id = serializers.UUIDField(source="category.id", read_only=True)
    logo = AbsoluteURLImageField(read_only=True)
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Restaurant
        fields = [
            "id", "brand_name", "logo", "short_description",
            "city", "short_address",
            "category_id", "category_name", "category_icon",
            "distance_km",
        ]
        read_only_fields = fields

    def get_distance_km(self, obj):
        """Returns distance in km rounded to 2 decimal places, or null."""
        return getattr(obj, "distance", None)
from rest_framework import serializers
from apps.utils.custom_fields import AbsoluteURLImageField
from .models import MenuCategory, MenuItem, ModifierGroup, ModifierOption
from apps.restaurants.models import RestaurantCategory

# --- Modifier Options Serializers Section ----------------------------------------------

class ModifierOptionSerializer(serializers.ModelSerializer):
    """ read/write serializer for a single modifier option."""
 
    class Meta:
        model  = ModifierOption
        fields = ["id", "name", "price", "option_type", "sort_order"]
        read_only_fields = ["id"]

# --- Modifier Group Serializer Sections  -------------------------------------------------

class ModifierGroupSerializer(serializers.ModelSerializer):
    """ Read Serializer includes nested options """

    options = ModifierOptionSerializer(many=True, read_only=True)
    option_count = serializers.IntegerField(read_only=True)

    class Meta:
        model  = ModifierGroup
        fields = ["id", "name", "type", "min_select", "max_select", "sort_order", "option_count", "options"]
        read_only_fields = ["id", "option_count", "options"]

class ModifierGroupWriteSerializer(serializers.ModelSerializer):
    """ Write/Update modifier group """

    class Meta:
        model  = ModifierGroup
        fields = ["id", "name", "type", "min_select", "max_select", "sort_order"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        """ min must not exceed max """

        min_s = attrs.get("min_select", getattr(self.instance, "min_select", 0))
        max_s = attrs.get("max_select", getattr(self.instance, "max_select", 1))
        if min_s > max_s:
            raise serializers.ValidationError({"min_select": "min_select cannot exceed max_select."})
        return attrs
    
# --- Menu Item Serializers Sections  ------------------------------------------------------------------

DIETARY_VALUES = [v for v, _ in MenuItem.DIETARY_CHOICES]

class MenuItemListSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()
    category_id = serializers.SerializerMethodField()
    photo = AbsoluteURLImageField(read_only=True)

    class Meta:
        model  = MenuItem
        fields = [
            "id", "name", "photo", "price", "description",
            "extra_prep_time", "calories", "dietary_info",
            "is_available", "sort_order", "category_id", "category_name",
        ]
        read_only_fields = fields

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None
    
    def get_category_id(self, obj):
        return str(obj.category.id) if obj.category else None

class MenuItemDetailSerializer(serializers.ModelSerializer):
    category_name   = serializers.SerializerMethodField()
    category_id     = serializers.SerializerMethodField()
    modifier_groups = ModifierGroupSerializer(many=True, read_only=True)
    photo = AbsoluteURLImageField(read_only=True)
    
    def get_category_name(self, obj):
        return obj.category.name if obj.category else None
    
    def get_category_id(self, obj):
        return str(obj.category.id) if obj.category else None

    class Meta:
        model  = MenuItem
        fields = [
            "id", "name", "photo", "price", "description",
            "extra_prep_time", "calories", "dietary_info",
            "is_available", "sort_order",
            "category_id", "category_name", "modifier_groups",
        ]
        read_only_fields = ["id", "category_id", "category_name", "modifier_groups"]

class MenuItemWriteSerializer(serializers.ModelSerializer):
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=MenuCategory.objects.all(),
        source="category",
        write_only=True,
        required=True
    )

    class Meta:
        model  = MenuItem
        fields = [
            "id", "category_id", "name", "photo", "price", "description",
            "extra_prep_time", "calories", "dietary_info",
            "is_available", "sort_order",
        ]
        read_only_fields = ["id"]

    def validate_category_id(self, value):
        if not value:
            raise serializers.ValidationError("Category is required.")
        # Ensure the category belongs to the same branch (context)
        branch = self.context.get("branch")
        if branch and not MenuCategory.objects.filter(id=value.id, branch=branch).exists():
            raise serializers.ValidationError("Category does not belong to this branch.")
        return value

    def validate_dietary_info(self, v):
        """Validate dietary info tags"""
        invalid = set(v) - set(DIETARY_VALUES)
        if invalid:
            raise serializers.ValidationError(f"Invalid dietary tags: {sorted(invalid)}.")
        return list(set(v)) if v else []

    def validate_dietary_info(self, v):
        invalid = set(v) - set(DIETARY_VALUES)
        if invalid:
            raise serializers.ValidationError(f"Invalid dietary tags: {sorted(invalid)}.")
        return list(set(v))
    
# --- MenuCategory Serializers Section ------------------------------------------------

class MenuCategoryListSerializer(serializers.ModelSerializer):
    """
    List serializer -- item_count is annotated by the service.
    """

    # item_count = serializers.IntegerField(read_only=True)   # annotated
 
    class Meta:
        model  = MenuCategory
        fields = ["id", "name", "is_active", "sort_order"]
        read_only_fields = ["id"]
 
 
class MenuCategoryDetailSerializer(serializers.ModelSerializer):
    """
    Detail serializer -- includes items with their modifier groups.
    """

    items = MenuItemDetailSerializer(many=True, read_only=True)
 
    class Meta:
        model  = MenuCategory
        fields = ["id", "name", "is_active", "sort_order", "items"]
        read_only_fields = ["id", "items"]
 
 
class MenuCategoryWriteSerializer(serializers.ModelSerializer):
    """ create/update a category."""
 
    class Meta:
        model = MenuCategory
        fields = ["id", "name", "is_active", "sort_order"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        """Check that the category name is unique within the branch."""
        branch = self.context.get("branch")
        if not branch:
            return value
        
        # Check for existing category with same name in this branch
        # Exclude current instance if updating
        queryset = MenuCategory.objects.filter(branch=branch, name=value)
        if self.instance:
            queryset = queryset.exclude(id=self.instance.id)
        
        if queryset.exists():
            raise serializers.ValidationError(
                f"A category named '{value}' already exists for this branch."
            )
        return value
    
# --- RestaurantCategory + items (replaces MenuCategory) ----------------------

class RestaurantCategoryMenuSerializer(serializers.ModelSerializer):
    """Category detail with its menu items and modifier groups."""
    items = MenuItemDetailSerializer(many=True, read_only=True)

    class Meta:
        model  = RestaurantCategory
        fields = ["id", "name", "items"]
        read_only_fields = ["id", "items"]

# --- Bulk Menu Item Add Serializer(Step 2) --------------------------------------------------------------

class ModifierOptionWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    price = serializers.DecimalField(max_digits=8, decimal_places=2, default=0)
    option_type = serializers.ChoiceField(choices=ModifierOption.OptionType.choices, default=ModifierOption.OptionType.FREE)
    sort_order = serializers.IntegerField(default=0)


class ModifierGroupBulkSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    type = serializers.ChoiceField(choices=ModifierGroup.Type.choices, default=ModifierGroup.Type.OPTIONAL)
    min_select = serializers.IntegerField(default=0)
    max_select = serializers.IntegerField(default=5)
    sort_order = serializers.IntegerField(default=0)
    options = ModifierOptionWriteSerializer(many=True, default=list)

    def validate(self, attrs):
        if attrs["min_select"] > attrs["max_select"]:
            raise serializers.ValidationError({"min_select": "min_select cannot exceed max_select."})
        return attrs
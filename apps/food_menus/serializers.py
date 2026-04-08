from rest_framework import serializers
from apps.utils.custom_fields import AbsoluteURLImageField
from .models import MenuCategory, MenuItem, ModifierGroup, ModifierOption

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
    """ Category Item List """
    category_name = serializers.CharField(source="category.name", read_only=True)
    photo = AbsoluteURLImageField(read_only=True)

    class Meta:
        model  = MenuItem
        fields = [
            "id", "name", "photo", "price", "description",
            "extra_prep_time", "calories", "dietary_info",
            "is_available", "sort_order", "category_name",
        ]
        read_only_fields = ["id", "category_name"]

class MenuItemDetailSerializer(serializers.ModelSerializer):
    """ Full details serializer of Menus with their groups and options """
    category_name   = serializers.CharField(source="category.name", read_only=True)
    modifier_groups = ModifierGroupSerializer(many=True, read_only=True)
    photo = AbsoluteURLImageField(read_only=True)

    class Meta:
        model  = MenuItem
        fields = [
            "id", "name", "photo", "price", "description",
            "extra_prep_time", "calories", "dietary_info",
            "is_available", "sort_order",
            "category_name", "modifier_groups",
        ]
        read_only_fields = ["id", "category_name", "modifier_groups"]

class MenuItemWriteSerializer(serializers.ModelSerializer):
    """ Add item flow """

    category_id = serializers.PrimaryKeyRelatedField(queryset=MenuCategory.objects.none(), source="category", write_only=True)  

    class Meta:
        model  = MenuItem
        fields = [
            "id", "category_id", "name", "photo", "price", "description",
            "extra_prep_time", "calories", "dietary_info",
            "is_available", "sort_order",
        ]
        read_only_fields = ["id"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # restrict category choices to the branch being managed
        request = self.context.get("request")
        branch  = self.context.get("branch")
        if branch:
            self.fields["category_id"].queryset = MenuCategory.objects.filter(branch=branch)
 
    def validate_dietary_info(self, v):
        # reject any unknown dietary tags
        invalid = set(v) - set(DIETARY_VALUES)
        if invalid:
            raise serializers.ValidationError(f"Invalid dietary tags: {sorted(invalid)}.")
        return list(set(v))   # deduplicate
    
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
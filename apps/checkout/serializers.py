from rest_framework import serializers
from apps.food_menus.models import ModifierOption
from .models import Cart, CartItem


class AddToCartSerializer(serializers.Serializer):
    branch_id = serializers.UUIDField()
    menu_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    selected_options = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
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
    cart_item_id = serializers.UUIDField(source="id")
    menu_item_id = serializers.UUIDField(source="menu_item.id")
    name = serializers.CharField(source="menu_item.name")
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    selected_options = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
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
                    "id": str(opt.id),
                    "group_name": opt.group.name,
                    "name": opt.name,
                    "price": str(opt.price),
                })
            except ModifierOption.DoesNotExist:
                pass
        return options


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
            "cart_id", "branch_id", "branch_name",
            "restaurant_name", "items", "total",
        ]
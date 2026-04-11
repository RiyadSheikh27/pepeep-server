from decimal import Decimal
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.utils.custom_response import APIResponse
from apps.authentication.permissions import IsCustomer
from apps.restaurants.models import Branch, Restaurant
from apps.food_menus.models import MenuItem, ModifierOption, ModifierGroup
from .models import Cart, CartItem
from .serializers import (
    AddToCartSerializer,
    UpdateCartItemSerializer,
    ClearCartSerializer,
    CartSerializer,
)

# --- Helpers ------------------------------------------------------------------

def _calculate_options_price(selected_option_ids: list, item: MenuItem) -> tuple[Decimal, list]:
    if not selected_option_ids:
        required_groups = ModifierGroup.objects.filter(item=item, type="required")
        if required_groups.exists():
            raise ValueError(
                f"Please select options for required groups: "
                f"{', '.join(required_groups.values_list('name', flat=True))}"
            )
        return Decimal("0.00"), []

    groups = ModifierGroup.objects.filter(item=item).prefetch_related("options")

    all_options = {}
    for group in groups:
        for opt in group.options.all():
            all_options[str(opt.id)] = (opt, group)

    group_selection_count = {}
    validated_ids = []
    total_price = Decimal("0.00")

    for opt_id in selected_option_ids:
        opt_id = str(opt_id)
        if opt_id not in all_options:
            raise ValueError(f"Option {opt_id} does not belong to this menu item.")

        opt, group = all_options[opt_id]
        group_id = str(group.id)
        group_selection_count[group_id] = group_selection_count.get(group_id, 0) + 1
        validated_ids.append(opt_id)
        total_price += opt.price

    for group in groups:
        group_id = str(group.id)
        count = group_selection_count.get(group_id, 0)

        if group.type == "required" and count < group.min_select:
            raise ValueError(
                f"Group '{group.name}' requires at least {group.min_select} selection(s)."
            )
        if count > group.max_select:
            raise ValueError(
                f"Group '{group.name}' allows at most {group.max_select} selection(s)."
            )

    return total_price, validated_ids


# --- Restaurant & Branch Views ------------------------------------------------------------------

class RestaurantListView(APIView):
    """
    GET /api/v1/cart/restaurants/
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request):
        restaurants = (
            Restaurant.objects
            .filter(is_active=True)
            .select_related("category")
            .order_by("brand_name")
        )
        data = [
            {
                "id": str(r.id),
                "brand_name": r.brand_name,
                "category": r.category.name if r.category else None,
                "city": r.city,
                "short_address": r.short_address,
            }
            for r in restaurants
        ]
        return APIResponse.success(data=data, meta={"count": len(data)})

class BranchListView(APIView):
    """
    GET /api/v1/cart/restaurants/{restaurant_id}/branches/
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request, restaurant_id):
        try:
            restaurant = Restaurant.objects.get(id=restaurant_id, is_active=True)
        except Restaurant.DoesNotExist:
            return APIResponse.error(message="Restaurant not found.", status_code=404)

        branches = Branch.objects.filter(restaurant=restaurant, is_active=True)
        data = [
            {
                "id": str(b.id),
                "name": b.name,
                "city": b.city,
                "full_address": b.full_address,
                "min_order": str(b.min_order),
                "phone": b.phone,
            }
            for b in branches
        ]
        return APIResponse.success(data=data, meta={"count": len(data)})


class BranchMenuView(APIView):
    """
    GET /api/v1/cart/branches/{branch_id}/menu/
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request, branch_id):
        try:
            branch = Branch.objects.get(id=branch_id, is_active=True)
        except Branch.DoesNotExist:
            return APIResponse.error(message="Branch not found.", status_code=404)

        items = (
            MenuItem.objects
            .filter(branch=branch, is_available=True)
            .select_related("category")
            .prefetch_related("modifier_groups__options")
            .order_by("category__sort_order", "sort_order", "name")
        )

        categories = {}
        for item in items:
            cat_id = str(item.category.id) if item.category else "uncategorized"
            cat_name = item.category.name if item.category else "Uncategorized"

            if cat_id not in categories:
                categories[cat_id] = {
                    "category_id": cat_id,
                    "category_name": cat_name,
                    "items": [],
                }

            groups = []
            for group in item.modifier_groups.all():
                groups.append({
                    "id": str(group.id),
                    "name": group.name,
                    "type": group.type,
                    "min_select": group.min_select,
                    "max_select": group.max_select,
                    "options": [
                        {
                            "id": str(opt.id),
                            "name": opt.name,
                            "price": str(opt.price),
                            "option_type": opt.option_type,
                        }
                        for opt in group.options.all()
                    ],
                })

            categories[cat_id]["items"].append({
                "id": str(item.id),
                "name": item.name,
                "price": str(item.price),
                "description": item.description,
                "calories": item.calories,
                "dietary_info": item.dietary_info,
                "modifier_groups": groups,
            })

        return APIResponse.success(
            data=list(categories.values()),
            meta={"branch_name": branch.name, "count": len(categories)},
        )

class CartView(APIView):
    """
    GET    /api/v1/cart/
    POST   /api/v1/cart/
    DELETE /api/v1/cart/
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request):
        carts = (
            Cart.objects
            .filter(customer=request.user)
            .select_related("branch", "branch__restaurant")
            .prefetch_related("items__menu_item")
        )
        return APIResponse.success(
            data=CartSerializer(carts, many=True).data,
            meta={"count": carts.count()},
        )

    def post(self, request):
        s = AddToCartSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        # Fetch branch
        try:
            branch = Branch.objects.select_related("restaurant").get(
                id=d["branch_id"], is_active=True
            )
        except Branch.DoesNotExist:
            return APIResponse.error(message="Branch not found.", status_code=404)

        # Fetch menu item
        try:
            item = MenuItem.objects.get(
                id=d["menu_item_id"], branch=branch, is_available=True
            )
        except MenuItem.DoesNotExist:
            return APIResponse.error(message="Menu item not found or unavailable.", status_code=404)

        # Validate options
        try:
            options_price, validated_option_ids = _calculate_options_price(
                [str(x) for x in d["selected_options"]], item
            )
        except ValueError as e:
            return APIResponse.error(errors={"selected_options": [str(e)]}, message=str(e))

        # Block multi-branch cart
        existing_other = Cart.objects.filter(
            customer=request.user
        ).exclude(branch=branch).first()

        if existing_other:
            return APIResponse.error(
                message=(
                    f"You already have an active cart at '{existing_other.branch.name}'. "
                    f"Please clear it before ordering from a different branch."
                ),
                status_code=400,
            )

        # Get or create cart
        cart, _ = Cart.objects.get_or_create(customer=request.user, branch=branch)

        # Check if same item + same options already in cart
        existing_item = None
        for ci in cart.items.all():
            if (
                str(ci.menu_item_id) == str(item.id)
                and sorted(ci.selected_options) == sorted(validated_option_ids)
            ):
                existing_item = ci
                break

        if existing_item:
            existing_item.quantity += d["quantity"]
            existing_item.save(update_fields=["quantity", "updated_at"])
        else:
            CartItem.objects.create(
                cart=cart,
                menu_item=item,
                quantity=d["quantity"],
                selected_options=validated_option_ids,
                item_price=item.price,
                options_price=options_price,
            )

        cart.refresh_from_db()
        return APIResponse.success(
            message="Item added to cart.",
            data=CartSerializer(cart).data,
            status_code=201,
        )

    def delete(self, request):
        s = ClearCartSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        try:
            cart = Cart.objects.get(
                customer=request.user, branch_id=s.validated_data["branch_id"]
            )
            cart.delete()
        except Cart.DoesNotExist:
            return APIResponse.error(message="No active cart found for this branch.", status_code=404)

        return APIResponse.success(message="Cart cleared.")


class CartItemView(APIView):
    """
    PATCH  /api/v1/cart/items/{cart_item_id}/
    DELETE /api/v1/cart/items/{cart_item_id}/
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def _get_cart_item(self, request, cart_item_id):
        try:
            return CartItem.objects.select_related(
                "cart", "cart__branch", "cart__branch__restaurant", "menu_item"
            ).get(id=cart_item_id, cart__customer=request.user)
        except CartItem.DoesNotExist:
            return None

    def patch(self, request, cart_item_id):
        ci = self._get_cart_item(request, cart_item_id)
        if not ci:
            return APIResponse.error(message="Cart item not found.", status_code=404)

        s = UpdateCartItemSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        ci.quantity = s.validated_data["quantity"]
        ci.save(update_fields=["quantity", "updated_at"])

        return APIResponse.success(
            message="Cart item updated.",
            data=CartSerializer(ci.cart).data,
        )

    def delete(self, request, cart_item_id):
        ci = self._get_cart_item(request, cart_item_id)
        if not ci:
            return APIResponse.error(message="Cart item not found.", status_code=404)

        cart = ci.cart
        ci.delete()

        if not cart.items.exists():
            cart.delete()
            return APIResponse.success(message="Item removed. Cart is now empty.")

        return APIResponse.success(
            message="Item removed from cart.",
            data=CartSerializer(cart).data,
        )
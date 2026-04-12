import secrets
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.utils.custom_response import APIResponse
from apps.authentication.permissions import IsCustomer, IsEmployee, IsOwner, IsAdmin, IsOwnerOrAdmin
from apps.restaurants.models import Branch, Restaurant
from apps.food_menus.models import MenuItem, ModifierOption, ModifierGroup
from .models import Cart, CartItem, CustomerCar, Order, OrderItem, OrderRating
from .serializers import (
    AddToCartSerializer, UpdateCartItemSerializer, ClearCartSerializer,
    CartSerializer, CustomerCarSerializer,
    PlaceOrderSerializer, OrderSerializer, OrderListSerializer,
    CashConfirmSerializer, OrderStatusUpdateSerializer, OrderRatingSerializer,
)

# --- Constants ----------------------------------------------------------------
SERVICE_FEE = Decimal("5.00")
VAT_RATE    = Decimal("0.15")


# --- Helpers ------------------------------------------------------------------

def _calculate_options_price(selected_option_ids: list, item: MenuItem):
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
            raise ValueError(f"Group '{group.name}' requires at least {group.min_select} selection(s).")
        if count > group.max_select:
            raise ValueError(f"Group '{group.name}' allows at most {group.max_select} selection(s).")

    return total_price, validated_ids


def _build_order_snapshot(cart: Cart):
    """Build order items snapshot from cart."""
    items_data = []
    subtotal = Decimal("0.00")
    for ci in cart.items.select_related("menu_item").all():
        option_names = []
        for opt_id in ci.selected_options:
            try:
                opt = ModifierOption.objects.get(id=opt_id)
                option_names.append({"name": opt.name, "price": str(opt.price)})
            except ModifierOption.DoesNotExist:
                pass
        item_subtotal = (ci.item_price + ci.options_price) * ci.quantity
        subtotal += item_subtotal
        items_data.append({
            "menu_item":       ci.menu_item,
            "name":            ci.menu_item.name,
            "price":           ci.item_price,
            "options_price":   ci.options_price,
            "quantity":        ci.quantity,
            "selected_options": option_names,
        })
    return items_data, subtotal


def _can_manage_order(user, order):
    """Check if employee/owner/admin can manage this order."""
    if user.role == "admin":
        return True
    if user.role == "owner":
        return order.branch.restaurant.owner_id == user.id
    if user.role == "employee":
        emp = getattr(user, "employee_profile", None)
        return emp and str(emp.branch_id) == str(order.branch_id)
    return False


# --- CUSTOMER CAR VIEWS ------------------------------------------------------------------

class CustomerCarListCreateView(APIView):
    """
    GET  /cart/cars/       — list my cars
    POST /cart/cars/       — add a new car
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request):
        cars = CustomerCar.objects.filter(customer=request.user).order_by("-created_at")
        return APIResponse.success(
            data=CustomerCarSerializer(cars, many=True).data,
            meta={"count": cars.count()},
        )

    def post(self, request):
        s = CustomerCarSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        car = s.save(customer=request.user)
        return APIResponse.success(
            message="Car added.",
            data=CustomerCarSerializer(car).data,
            status_code=201,
        )


class CustomerCarDetailView(APIView):
    """
    PATCH  /cart/cars/{id}/  — update car
    DELETE /cart/cars/{id}/  — remove car
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def _get_car(self, request, pk):
        try:
            return CustomerCar.objects.get(id=pk, customer=request.user)
        except CustomerCar.DoesNotExist:
            return None

    def patch(self, request, pk):
        car = self._get_car(request, pk)
        if not car:
            return APIResponse.error(message="Car not found.", status_code=404)
        s = CustomerCarSerializer(car, data=request.data, partial=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        s.save()
        return APIResponse.success(message="Car updated.", data=s.data)

    def delete(self, request, pk):
        car = self._get_car(request, pk)
        if not car:
            return APIResponse.error(message="Car not found.", status_code=404)
        car.delete()
        return APIResponse.success(message="Car removed.")


# --- CART VIEWS ------------------------------------------------------------------

class RestaurantListView(APIView):
    """GET /cart/restaurants/"""
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request):
        restaurants = (
            Restaurant.objects.filter(is_active=True)
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
    """GET /cart/restaurants/{restaurant_id}/branches/"""
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
    """GET /cart/branches/{branch_id}/menu/"""
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
            cat_id   = str(item.category.id) if item.category else "uncategorized"
            cat_name = item.category.name if item.category else "Uncategorized"
            if cat_id not in categories:
                categories[cat_id] = {"category_id": cat_id, "category_name": cat_name, "items": []}

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
    GET /cart/
    POST /cart/
    DELETE /cart/
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request):
        carts = (
            Cart.objects.filter(customer=request.user)
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

        try:
            branch = Branch.objects.select_related("restaurant").get(id=d["branch_id"], is_active=True)
        except Branch.DoesNotExist:
            return APIResponse.error(message="Branch not found.", status_code=404)

        try:
            item = MenuItem.objects.get(id=d["menu_item_id"], branch=branch, is_available=True)
        except MenuItem.DoesNotExist:
            return APIResponse.error(message="Menu item not found or unavailable.", status_code=404)

        try:
            options_price, validated_option_ids = _calculate_options_price(
                [str(x) for x in d["selected_options"]], item
            )
        except ValueError as e:
            return APIResponse.error(errors={"selected_options": [str(e)]}, message=str(e))

        existing_other = Cart.objects.filter(customer=request.user).exclude(branch=branch).first()
        if existing_other:
            return APIResponse.error(
                message=f"You already have an active cart at '{existing_other.branch.name}'. Please clear it first.",
                status_code=400,
            )

        cart, _ = Cart.objects.get_or_create(customer=request.user, branch=branch)

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
            cart = Cart.objects.get(customer=request.user, branch_id=s.validated_data["branch_id"])
            cart.delete()
        except Cart.DoesNotExist:
            return APIResponse.error(message="No active cart found for this branch.", status_code=404)
        return APIResponse.success(message="Cart cleared.")


class CartItemView(APIView):
    """
    PATCH  /cart/items/{cart_item_id}/
    DELETE /cart/items/{cart_item_id}/
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
        return APIResponse.success(message="Cart item updated.", data=CartSerializer(ci.cart).data)

    def delete(self, request, cart_item_id):
        ci = self._get_cart_item(request, cart_item_id)
        if not ci:
            return APIResponse.error(message="Cart item not found.", status_code=404)
        cart = ci.cart
        ci.delete()
        if not cart.items.exists():
            cart.delete()
            return APIResponse.success(message="Item removed. Cart is now empty.")
        return APIResponse.success(message="Item removed from cart.", data=CartSerializer(cart).data)


# --- ORDER VIEWS — CUSTOMER -----------------------------------------------------------------------

class PlaceOrderView(APIView):
    """
    POST /orders/place/
    Creates order from active cart for a branch.
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    @transaction.atomic
    def post(self, request):
        s = PlaceOrderSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        # Validate branch
        try:
            branch = Branch.objects.select_related("restaurant").get(id=d["branch_id"], is_active=True)
        except Branch.DoesNotExist:
            return APIResponse.error(message="Branch not found.", status_code=404)

        # Validate car belongs to customer
        try:
            car = CustomerCar.objects.get(id=d["car_id"], customer=request.user)
        except CustomerCar.DoesNotExist:
            return APIResponse.error(message="Car not found.", status_code=404)

        # Get cart
        try:
            cart = Cart.objects.prefetch_related("items__menu_item").get(
                customer=request.user, branch=branch
            )
        except Cart.DoesNotExist:
            return APIResponse.error(message="No active cart for this branch.", status_code=404)

        if not cart.items.exists():
            return APIResponse.error(message="Cart is empty.", status_code=400)

        # Check min order
        cart_total = cart.total
        if cart_total < branch.min_order:
            return APIResponse.error(
                message=f"Minimum order is {branch.min_order} SAR. Your cart total is {cart_total} SAR.",
                status_code=400,
            )

        # Build snapshot
        items_data, subtotal = _build_order_snapshot(cart)
        vat   = (subtotal + SERVICE_FEE) * VAT_RATE
        total = subtotal + SERVICE_FEE + vat

        # Create order
        order = Order.objects.create(
            customer=request.user,
            branch=branch,
            car=car,
            note=d["note"],
            pickup_time=d["pickup_time"],
            payment_method=d["payment_method"],
            subtotal=subtotal,
            service_fee=SERVICE_FEE,
            vat=vat.quantize(Decimal("0.01")),
            total=total.quantize(Decimal("0.01")),
            qr_token=secrets.token_hex(32),
        )

        # Create order items snapshot
        for item_data in items_data:
            OrderItem.objects.create(
                order=order,
                menu_item=item_data["menu_item"],
                name=item_data["name"],
                price=item_data["price"],
                options_price=item_data["options_price"],
                quantity=item_data["quantity"],
                selected_options=item_data["selected_options"],
            )

        # Clear cart
        cart.delete()

        return APIResponse.success(
            message="Order placed successfully.",
            data=OrderSerializer(order).data,
            status_code=201,
        )


class CustomerOrderListView(APIView):
    """
    GET /orders/  — customer's own order history
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request):
        orders = (
            Order.objects
            .filter(customer=request.user)
            .select_related("branch", "branch__restaurant", "car")
            .prefetch_related("items")
            .order_by("-created_at")
        )
        return APIResponse.success(
            data=OrderListSerializer(orders, many=True).data,
            meta={"count": orders.count()},
        )


class CustomerOrderDetailView(APIView):
    """
    GET /orders/{order_id}/  — full order detail for customer
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request, order_id):
        try:
            order = (
                Order.objects
                .select_related("branch", "branch__restaurant", "car")
                .prefetch_related("items")
                .get(id=order_id, customer=request.user)
            )
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found.", status_code=404)
        return APIResponse.success(data=OrderSerializer(order).data)


class CustomerOrderCancelView(APIView):
    """
    POST /orders/{order_id}/cancel/
    Customer can cancel only if order is still pending.
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    @transaction.atomic
    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, customer=request.user)
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found.", status_code=404)

        if order.status != Order.Status.PENDING:
            return APIResponse.error(
                message="Order can only be cancelled while it is pending.",
                status_code=400,
            )

        order.status = Order.Status.CANCELLED
        order.cancelled_at = timezone.now()
        order.save(update_fields=["status", "cancelled_at", "updated_at"])

        return APIResponse.success(message="Order cancelled.")


class CustomerPeepView(APIView):
    """
    POST /orders/{order_id}/peep/
    Customer honks — notifies employee that customer has arrived.
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def post(self, request, order_id):
        try:
            order = Order.objects.select_related("branch").get(
                id=order_id,
                customer=request.user,
                status__in=[Order.Status.ACCEPTED, Order.Status.PREPARING, Order.Status.READY],
            )
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found or not active.", status_code=404)

        # TODO: trigger WebSocket notification to branch employees
        # channel_layer.group_send(f"branch_{order.branch_id}", {...})

        return APIResponse.success(
            message="Peep sent! The restaurant has been notified you have arrived.",
            data={"order_number": order.order_number},
        )


class CustomerConfirmDeliveryView(APIView):
    """
    POST /orders/{order_id}/confirm-delivery/
    Customer confirms they received the order (alternative to QR scan).
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    @transaction.atomic
    def post(self, request, order_id):
        try:
            order = Order.objects.get(
                id=order_id,
                customer=request.user,
                status=Order.Status.READY,
            )
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found or not ready.", status_code=404)

        order.status       = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
        order.save(update_fields=["status", "delivered_at", "updated_at"])

        # TODO: trigger WebSocket notification to branch employees
        return APIResponse.success(
            message="Order marked as delivered. Enjoy your meal!",
            data=OrderSerializer(order).data,
        )


class CustomerOrderQRView(APIView):
    """
    GET /orders/{order_id}/qr/
    Returns the QR token for the customer to display for scanning.
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request, order_id):
        try:
            order = Order.objects.get(
                id=order_id,
                customer=request.user,
                status=Order.Status.READY,
            )
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found or not ready.", status_code=404)

        return APIResponse.success(
            data={
                "order_number": order.order_number,
                "qr_token": order.qr_token,
            }
        )


class CustomerOrderRatingView(APIView):
    """
    POST /orders/{order_id}/rate/
    Customer rates and gives feedback after delivery.
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(
                id=order_id,
                customer=request.user,
                status=Order.Status.DELIVERED,
            )
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found or not delivered yet.", status_code=404)

        if hasattr(order, "rating"):
            return APIResponse.error(message="You have already rated this order.", status_code=400)

        s = OrderRatingSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        rating = s.save(order=order, customer=request.user)
        return APIResponse.success(
            message="Thank you for your feedback!",
            data=OrderRatingSerializer(rating).data,
            status_code=201,
        )


# --- ORDER VIEWS — EMPLOYEE / OWNER / ADMIN -----------------------------------------------------------------------    

class StaffOrderListView(APIView):
    """
    GET /staff/orders/
    Employee → branch orders only
    Owner → all branch orders of their restaurant
    Admin → all orders
    Query params: status, page, page_size
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user   = request.user
        status = request.query_params.get("status", "")

        if user.role == "employee":
            emp = getattr(user, "employee_profile", None)
            if not emp:
                return APIResponse.error(message="Employee profile not found.", status_code=404)
            qs = Order.objects.filter(branch=emp.branch)

        elif user.role == "owner":
            qs = Order.objects.filter(branch__restaurant__owner=user)

        elif user.role == "admin":
            qs = Order.objects.all()

        else:
            return APIResponse.error(message="Unauthorized.", status_code=403)

        if status:
            qs = qs.filter(status=status)

        qs = (
            qs.select_related("branch", "branch__restaurant", "car", "customer")
            .prefetch_related("items")
            .order_by("-created_at")
        )

        # Pagination
        try:
            page = max(1, int(request.query_params.get("page", 1)))
            page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))
        except (ValueError, TypeError):
            page, page_size = 1, 20

        total = qs.count()
        start = (page - 1) * page_size
        data  = OrderListSerializer(qs[start:start + page_size], many=True).data

        return APIResponse.success(
            data=data,
            meta={
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": max(1, -(-total // page_size)),
            },
        )


class StaffOrderDetailView(APIView):
    """
    GET /staff/orders/{order_id}/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = (
                Order.objects
                .select_related("branch", "branch__restaurant", "car", "customer")
                .prefetch_related("items")
                .get(id=order_id)
            )
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found.", status_code=404)

        if not _can_manage_order(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        return APIResponse.success(data=OrderSerializer(order).data)


class StaffOrderAcceptView(APIView):
    """
    POST /staff/orders/{order_id}/accept/
    Body: { "prep_time": 22 }   ← estimated minutes
    Employee accepts order → status: preparing
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, status=Order.Status.PENDING)
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found or already processed.", status_code=404)

        if not _can_manage_order(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        s = OrderStatusUpdateSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        now = timezone.now()
        order.status = Order.Status.PREPARING
        order.accepted_at  = now
        order.preparing_at = now
        order.save(update_fields=["status", "accepted_at", "preparing_at", "updated_at"])

        # TODO: WebSocket push to customer
        return APIResponse.success(
            message="Order accepted. Preparation started.",
            data=OrderSerializer(order).data,
        )


class StaffOrderModifyView(APIView):
    """
    POST /staff/orders/{order_id}/modify/
    Body: { "reason": "No onions, extra cheese" }
    Employee sends modification note to customer.
    Status stays pending.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, status=Order.Status.PENDING)
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found or not pending.", status_code=404)

        if not _can_manage_order(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        reason = request.data.get("reason", "").strip()
        if not reason:
            return APIResponse.error(errors={"reason": ["Modification reason is required."]})

        # Store modification note in order note field
        order.note = f"[Staff modification]: {reason}"
        order.save(update_fields=["note", "updated_at"])

        # TODO: WebSocket push to customer
        return APIResponse.success(
            message="Modification note sent to customer.",
            data={"order_number": order.order_number, "note": order.note},
        )


class StaffOrderCancelView(APIView):
    """
    POST /staff/orders/{order_id}/cancel/
    Body: { "reason": "Stock out of ingredients" }
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, order_id):
        try:
            order = Order.objects.get(
                id=order_id,
                status__in=[Order.Status.PENDING, Order.Status.PREPARING],
            )
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found or cannot be cancelled.", status_code=404)

        if not _can_manage_order(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        reason = request.data.get("reason", "").strip()
        order.status = Order.Status.CANCELLED
        order.cancelled_at = timezone.now()
        order.note = f"[Cancelled by staff]: {reason}" if reason else order.note
        order.save(update_fields=["status", "cancelled_at", "note", "updated_at"])

        # TODO: WebSocket push to customer
        return APIResponse.success(message="Order cancelled.")


class StaffOrderReadyView(APIView):
    """
    POST /staff/orders/{order_id}/ready/
    Employee marks order as ready for pickup.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, status=Order.Status.PREPARING)
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found or not in preparing state.", status_code=404)

        if not _can_manage_order(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        order.status   = Order.Status.READY
        order.ready_at = timezone.now()
        order.save(update_fields=["status", "ready_at", "updated_at"])

        # TODO: WebSocket push to customer
        return APIResponse.success(
            message="Order marked as ready.",
            data=OrderSerializer(order).data,
        )


class StaffScanQRView(APIView):
    """
    POST /staff/orders/scan-qr/
    Body: { "qr_token": "..." }
    Employee scans customer QR → marks order delivered.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        qr_token = request.data.get("qr_token", "").strip()
        if not qr_token:
            return APIResponse.error(errors={"qr_token": ["This field is required."]})

        try:
            order = Order.objects.select_related("branch").get(
                qr_token=qr_token,
                status=Order.Status.READY,
            )
        except Order.DoesNotExist:
            return APIResponse.error(message="Invalid QR code or order not ready.", status_code=404)

        if not _can_manage_order(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        order.status       = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
        order.qr_token     = None   # invalidate
        order.save(update_fields=["status", "delivered_at", "qr_token", "updated_at"])

        # TODO: WebSocket push to customer
        return APIResponse.success(
            message="QR scanned. Order delivered successfully!",
            data={
                "order_number": order.order_number,
                "customer": str(order.customer_id),
                "items": order.items.count(),
            },
        )


class StaffCashConfirmView(APIView):
    """
    POST /staff/orders/{order_id}/confirm-cash/
    Body: { "amount_received": 77.05 }
    Employee confirms hand cash received → marks payment paid.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, order_id):
        try:
            order = Order.objects.get(
                id=order_id,
                payment_method=Order.PaymentMethod.HAND_CASH,
                payment_status=Order.PaymentStatus.PENDING,
            )
        except Order.DoesNotExist:
            return APIResponse.error(message="Order not found or payment already confirmed.", status_code=404)

        if not _can_manage_order(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        s = CashConfirmSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        order.payment_status      = Order.PaymentStatus.PAID
        order.cash_confirmed_by   = request.user
        order.save(update_fields=["payment_status", "cash_confirmed_by", "updated_at"])

        return APIResponse.success(
            message=f"Cash payment of {s.validated_data['amount_received']} SAR confirmed.",
            data=OrderSerializer(order).data,
        )
"""
All ordering business logic lives here.
No service layer — views own the logic as specified.
"""
import math
import secrets
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.utils.custom_response import APIResponse
from apps.authentication.permissions import IsCustomer, IsEmployee, IsOwner, IsAdmin
from apps.restaurants.models import Branch
from apps.food_menus.models import MenuItem, ModifierOption, ModifierGroup

from .models import Car, Cart, CartItem, Order, OrderItem, Payment, Feedback
from .serializers import (
    # car
    CarSerializer,
    # cart
    AddToCartSerializer, UpdateCartItemSerializer, ClearCartSerializer, CartSerializer,
    # checkout
    CheckoutInitSerializer, ConfirmOrderSerializer,
    # order
    OrderSerializer, OrderListSerializer, OrderETASerializer,
    # employee actions
    AcceptOrderSerializer, UpdateStatusSerializer, CancelOrderSerializer,
    CashReceiveSerializer, QRScanSerializer,
    # user actions
    MarkArrivedSerializer, FeedbackSerializer,
)
from .tasks import mark_user_arrived

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────

SERVICE_FEE = Decimal("5.00")
VAT_RATE    = Decimal("0.15")

# Average driving speed used for ETA mock (km/h)
AVG_SPEED_KMH = 40.0


# ─────────────────────────────────────────────
#  PRIVATE HELPERS
# ─────────────────────────────────────────────

def _haversine_km(lat1, lon1, lat2, lon2) -> float | None:
    """Return great-circle distance in km, or None if any coord is missing."""
    if not all([lat1, lon1, lat2, lon2]):
        return None
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


def _validate_options(selected_option_ids: list, item: MenuItem):
    """
    Validate selected modifier options against the item's modifier groups.
    Returns (total_options_price, validated_id_strings) or raises ValueError.
    """
    if not selected_option_ids:
        required_groups = ModifierGroup.objects.filter(item=item, type="required")
        if required_groups.exists():
            names = ", ".join(required_groups.values_list("name", flat=True))
            raise ValueError(f"Please select options for required groups: {names}")
        return Decimal("0.00"), []

    groups = ModifierGroup.objects.filter(item=item).prefetch_related("options")
    option_map = {}
    for g in groups:
        for opt in g.options.all():
            option_map[str(opt.id)] = (opt, g)

    group_count = {}
    validated   = []
    total_price = Decimal("0.00")

    for raw_id in selected_option_ids:
        oid = str(raw_id)
        if oid not in option_map:
            raise ValueError(f"Option {oid} does not belong to this menu item.")
        opt, group = option_map[oid]
        gid = str(group.id)
        group_count[gid] = group_count.get(gid, 0) + 1
        validated.append(oid)
        total_price += opt.price

    for g in groups:
        gid   = str(g.id)
        count = group_count.get(gid, 0)
        if g.type == "required" and count < g.min_select:
            raise ValueError(f"Group '{g.name}' requires at least {g.min_select} selection(s).")
        if count > g.max_select:
            raise ValueError(f"Group '{g.name}' allows at most {g.max_select} selection(s).")

    return total_price, validated


def _build_order_snapshot(cart: Cart):
    """Snapshot cart into order-item dicts. Returns (items_data, subtotal)."""
    items_data = []
    subtotal   = Decimal("0.00")

    for ci in cart.items.select_related("menu_item").all():
        opt_snapshots = []
        for oid in ci.selected_options:
            try:
                opt = ModifierOption.objects.get(id=oid)
                opt_snapshots.append({"name": opt.name, "price": str(opt.price)})
            except ModifierOption.DoesNotExist:
                pass

        line = (ci.item_price + ci.options_price) * ci.quantity
        subtotal += line
        items_data.append({
            "menu_item":       ci.menu_item,
            "name":            ci.menu_item.name,
            "price":           ci.item_price,
            "options_price":   ci.options_price,
            "quantity":        ci.quantity,
            "selected_options": opt_snapshots,
        })
    return items_data, subtotal


def _can_manage(user, order) -> bool:
    """True if user has authority over the order."""
    if user.role == "admin":
        return True
    if user.role == "owner":
        return order.branch.restaurant.owner_id == user.id
    if user.role == "employee":
        emp = getattr(user, "employee_profile", None)
        return emp and str(emp.branch_id) == str(order.branch_id)
    return False


def _order_or_404(order_id, extra_filter=None):
    """Fetch order with related data or return None."""
    qs = (
        Order.objects
        .select_related("branch", "branch__restaurant", "car", "payment", "customer")
        .prefetch_related("items")
    )
    if extra_filter:
        qs = qs.filter(**extra_filter)
    return qs.filter(id=order_id).first()


def _paginate(request, qs, serializer_class):
    try:
        page      = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))
    except (ValueError, TypeError):
        page, page_size = 1, 20

    total = qs.count()
    start = (page - 1) * page_size
    data  = serializer_class(qs[start:start + page_size], many=True).data

    return APIResponse.success(
        data=data,
        meta={
            "total":     total,
            "page":      page,
            "page_size": page_size,
            "pages":     max(1, -(-total // page_size)),
        },
    )


# ═════════════════════════════════════════════
#  CAR VIEWS
# ═════════════════════════════════════════════

class CarListCreateView(APIView):
    """
    GET  /checkout/cars/   — list my saved cars
    POST /checkout/cars/   — save a new car
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request):
        cars = Car.objects.filter(customer=request.user).order_by("-created_at")
        return APIResponse.success(
            data=CarSerializer(cars, many=True).data,
            meta={"count": cars.count()},
        )

    def post(self, request):
        s = CarSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        car = s.save(customer=request.user)
        return APIResponse.success(
            message="Car saved.",
            data=CarSerializer(car).data,
            status_code=201,
        )


class CarDetailView(APIView):
    """
    PATCH  /checkout/cars/{id}/
    DELETE /checkout/cars/{id}/
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def _get(self, request, pk):
        return Car.objects.filter(id=pk, customer=request.user).first()

    def patch(self, request, pk):
        car = self._get(request, pk)
        if not car:
            return APIResponse.error(message="Car not found.", status_code=404)
        s = CarSerializer(car, data=request.data, partial=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        s.save()
        return APIResponse.success(message="Car updated.", data=s.data)

    def delete(self, request, pk):
        car = self._get(request, pk)
        if not car:
            return APIResponse.error(message="Car not found.", status_code=404)
        car.delete()
        return APIResponse.success(message="Car removed.")


# ═════════════════════════════════════════════
#  CART VIEWS
# ═════════════════════════════════════════════

class CartView(APIView):
    """
    GET    /checkout/cart/          — view all active carts
    POST   /checkout/cart/          — add item to cart
    DELETE /checkout/cart/          — clear entire cart for a branch
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

        # Validate branch
        branch = Branch.objects.filter(id=d["branch_id"], is_active=True).select_related("restaurant").first()
        if not branch:
            return APIResponse.error(message="Branch not found.", status_code=404)

        # Validate item
        item = MenuItem.objects.filter(id=d["menu_item_id"], branch=branch, is_available=True).first()
        if not item:
            return APIResponse.error(message="Menu item not found or unavailable.", status_code=404)

        # Validate options
        try:
            options_price, validated_ids = _validate_options(
                [str(x) for x in d["selected_options"]], item
            )
        except ValueError as exc:
            return APIResponse.error(errors={"selected_options": [str(exc)]}, message=str(exc))

        # Prevent multi-branch carts
        other_cart = Cart.objects.filter(customer=request.user).exclude(branch=branch).first()
        if other_cart:
            return APIResponse.error(
                message=f"You already have a cart at '{other_cart.branch.name}'. Clear it first.",
                status_code=400,
            )

        cart, _ = Cart.objects.get_or_create(customer=request.user, branch=branch)

        # Merge if same item + same options
        existing = next(
            (ci for ci in cart.items.all()
             if str(ci.menu_item_id) == str(item.id)
             and sorted(ci.selected_options) == sorted(validated_ids)),
            None,
        )
        if existing:
            existing.quantity += d["quantity"]
            existing.save(update_fields=["quantity", "updated_at"])
        else:
            CartItem.objects.create(
                cart=cart,
                menu_item=item,
                quantity=d["quantity"],
                selected_options=validated_ids,
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
        cart = Cart.objects.filter(
            customer=request.user, branch_id=s.validated_data["branch_id"]
        ).first()
        if not cart:
            return APIResponse.error(message="No active cart for this branch.", status_code=404)
        cart.delete()
        return APIResponse.success(message="Cart cleared.")


class CartItemView(APIView):
    """
    PATCH  /checkout/cart/items/{id}/   — change quantity
    DELETE /checkout/cart/items/{id}/   — remove item
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def _get_item(self, request, pk):
        return (
            CartItem.objects
            .select_related("cart", "cart__branch", "cart__branch__restaurant", "menu_item")
            .filter(id=pk, cart__customer=request.user)
            .first()
        )

    def patch(self, request, pk):
        ci = self._get_item(request, pk)
        if not ci:
            return APIResponse.error(message="Cart item not found.", status_code=404)
        s = UpdateCartItemSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        ci.quantity = s.validated_data["quantity"]
        ci.save(update_fields=["quantity", "updated_at"])
        return APIResponse.success(message="Cart item updated.", data=CartSerializer(ci.cart).data)

    def delete(self, request, pk):
        ci = self._get_item(request, pk)
        if not ci:
            return APIResponse.error(message="Cart item not found.", status_code=404)
        cart = ci.cart
        ci.delete()
        if not cart.items.exists():
            cart.delete()
            return APIResponse.success(message="Item removed. Cart is now empty.")
        return APIResponse.success(message="Item removed from cart.", data=CartSerializer(cart).data)


# ═════════════════════════════════════════════
#  CHECKOUT — STEP 1: INITIATE
# ═════════════════════════════════════════════

class CheckoutInitView(APIView):
    """
    POST /checkout/initiate/

    For Stripe:  creates a PaymentIntent server-side, returns client_secret + intent_id.
    For Cash:    returns order summary only (no intent created).

    Does NOT create the Order — that happens in Step 2 (ConfirmOrderView).
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def post(self, request):
        s = CheckoutInitSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        branch = Branch.objects.filter(id=d["branch_id"], is_active=True).select_related("restaurant").first()
        if not branch:
            return APIResponse.error(message="Branch not found.", status_code=404)

        cart = (
            Cart.objects
            .filter(customer=request.user, branch=branch)
            .prefetch_related("items__menu_item")
            .first()
        )
        if not cart or not cart.items.exists():
            return APIResponse.error(message="Your cart is empty.", status_code=400)

        subtotal    = cart.total
        vat         = (subtotal + SERVICE_FEE) * VAT_RATE
        total       = (subtotal + SERVICE_FEE + vat).quantize(Decimal("0.01"))

        summary = {
            "branch_name":     branch.name,
            "restaurant_name": branch.restaurant.brand_name,
            "items":           [
                {
                    "name":     ci.menu_item.name,
                    "quantity": ci.quantity,
                    "subtotal": str(ci.subtotal),
                }
                for ci in cart.items.all()
            ],
            "subtotal":    str(subtotal),
            "service_fee": str(SERVICE_FEE),
            "vat":         str(vat.quantize(Decimal("0.01"))),
            "total":       str(total),
        }

        if d["payment_method"] == Payment.Method.STRIPE:
            try:
                import stripe
                from django.conf import settings
                stripe.api_key = settings.STRIPE_SECRET_KEY

                intent = stripe.PaymentIntent.create(
                    amount=int(total * 100),   # Stripe uses smallest currency unit (halalas)
                    currency="sar",
                    metadata={
                        "customer_id": str(request.user.id),
                        "branch_id":   str(branch.id),
                    },
                )
                return APIResponse.success(
                    message="Payment intent created. Complete payment on the client.",
                    data={
                        "payment_method":  "stripe",
                        "stripe_intent_id": intent["id"],
                        "client_secret":   intent["client_secret"],
                        "summary":         summary,
                    },
                )
            except Exception as exc:
                return APIResponse.error(
                    message="Failed to create payment intent.",
                    errors={"stripe": [str(exc)]},
                    status_code=502,
                )

        # Cash flow — no intent needed
        return APIResponse.success(
            message="Review your order and confirm.",
            data={"payment_method": "cash", "summary": summary},
        )


# ═════════════════════════════════════════════
#  CHECKOUT — STEP 2: CONFIRM ORDER
# ═════════════════════════════════════════════

class ConfirmOrderView(APIView):
    """
    POST /checkout/confirm/

    Verifies payment (Stripe) or sets cash-pending,
    creates the Order + OrderItems, clears the cart.
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    @transaction.atomic
    def post(self, request):
        s = ConfirmOrderSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        # ── Branch ──────────────────────────────────────────────────────────
        branch = Branch.objects.filter(id=d["branch_id"], is_active=True).select_related("restaurant").first()
        if not branch:
            return APIResponse.error(message="Branch not found.", status_code=404)

        # ── Cart ────────────────────────────────────────────────────────────
        cart = (
            Cart.objects
            .filter(customer=request.user, branch=branch)
            .prefetch_related("items__menu_item")
            .first()
        )
        if not cart or not cart.items.exists():
            return APIResponse.error(message="Your cart is empty.", status_code=400)

        subtotal    = cart.total
        if subtotal < branch.min_order:
            return APIResponse.error(
                message=f"Minimum order is {branch.min_order} SAR. Your cart is {subtotal} SAR.",
                status_code=400,
            )

        vat   = (subtotal + SERVICE_FEE) * VAT_RATE
        total = (subtotal + SERVICE_FEE + vat).quantize(Decimal("0.01"))

        # ── Car ─────────────────────────────────────────────────────────────
        car = None
        if d.get("car_id"):
            car = Car.objects.filter(id=d["car_id"], customer=request.user).first()
            if not car:
                return APIResponse.error(message="Car not found.", status_code=404)
        else:
            # Create car inline and save it for future use
            car = Car.objects.create(
                customer=request.user,
                car_model=d["car_model"],
                plate_number=d["plate_number"],
                color=d["car_color"].upper(),
            )

        # ── Payment ─────────────────────────────────────────────────────────
        method = d["payment_method"]

        if method == Payment.Method.STRIPE:
            try:
                import stripe
                from django.conf import settings
                stripe.api_key = settings.STRIPE_SECRET_KEY

                intent = stripe.PaymentIntent.retrieve(d["stripe_intent_id"])
                if intent["status"] != "succeeded":
                    return APIResponse.error(
                        message="Payment not confirmed. Please complete the payment first.",
                        errors={"stripe": [f"Intent status: {intent['status']}"]},
                        status_code=402,
                    )
                payment = Payment.objects.create(
                    method=Payment.Method.STRIPE,
                    status=Payment.Status.PAID,
                    amount=total,
                    stripe_intent_id=d["stripe_intent_id"],
                )
            except Exception as exc:
                return APIResponse.error(
                    message="Stripe verification failed.",
                    errors={"stripe": [str(exc)]},
                    status_code=502,
                )
        else:
            # Cash — payment is pending until employee receives it
            payment = Payment.objects.create(
                method=Payment.Method.CASH,
                status=Payment.Status.PENDING,
                amount=total,
            )

        # ── Order ────────────────────────────────────────────────────────────
        order = Order.objects.create(
            customer=request.user,
            branch=branch,
            car=car,
            payment=payment,
            note=d.get("note", ""),
            pickup_time=d["pickup_time"],
            subtotal=subtotal,
            service_fee=SERVICE_FEE,
            vat=vat.quantize(Decimal("0.01")),
            total=total,
            qr_token=secrets.token_hex(32),
        )

        # ── Order Items (snapshot) ───────────────────────────────────────────
        items_data, _ = _build_order_snapshot(cart)
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

        # ── Clear Cart ───────────────────────────────────────────────────────
        cart.delete()

        return APIResponse.success(
            message="Order placed successfully.",
            data=OrderSerializer(order).data,
            status_code=201,
        )


# ═════════════════════════════════════════════
#  ORDER — LIST  (role-scoped)
# ═════════════════════════════════════════════

class OrderListView(APIView):
    """
    GET /checkout/orders/

    customer  → own orders only
    employee  → branch orders
    owner     → all branches of their restaurant
    admin     → all orders

    Query params: status, page, page_size
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user   = request.user
        status = request.query_params.get("status", "")

        if user.role == "customer":
            qs = Order.objects.filter(customer=user)

        elif user.role == "employee":
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
            qs.select_related("branch", "branch__restaurant", "car", "payment", "customer")
            .prefetch_related("items")
            .order_by("-created_at")
        )
        return _paginate(request, qs, OrderListSerializer)


# ═════════════════════════════════════════════
#  ORDER — DETAIL
# ═════════════════════════════════════════════

class OrderDetailView(APIView):
    """
    GET /checkout/orders/{order_id}/

    Customer sees own order.
    Employee / owner / admin see via staff endpoint.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        user = request.user

        if user.role == "customer":
            order = _order_or_404(order_id, extra_filter={"customer": user})
        else:
            order = _order_or_404(order_id)
            if order and not _can_manage(user, order):
                return APIResponse.error(message="Unauthorized.", status_code=403)

        if not order:
            return APIResponse.error(message="Order not found.", status_code=404)

        return APIResponse.success(data=OrderSerializer(order).data)


# ═════════════════════════════════════════════
#  EMPLOYEE — RECEIVE CASH
# ═════════════════════════════════════════════

class ReceiveCashView(APIView):
    """
    POST /checkout/orders/{order_id}/receive-cash/

    Employee confirms cash was received.
    Payment status → PAID.
    Must happen BEFORE accepting the order.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, order_id):
        order = _order_or_404(order_id)
        if not order:
            return APIResponse.error(message="Order not found.", status_code=404)
        if not _can_manage(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        payment = order.payment
        if not payment or payment.method != Payment.Method.CASH:
            return APIResponse.error(message="This order is not a cash order.", status_code=400)
        if payment.status == Payment.Status.PAID:
            return APIResponse.error(message="Cash already marked as received.", status_code=400)

        s = CashReceiveSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        payment.status           = Payment.Status.PAID
        payment.cash_received_by = request.user
        payment.cash_received_at = timezone.now()
        payment.save(update_fields=["status", "cash_received_by", "cash_received_at", "updated_at"])

        return APIResponse.success(
            message=f"Cash of {s.validated_data['amount_received']} SAR received.",
            data=OrderSerializer(order).data,
        )


# ═════════════════════════════════════════════
#  EMPLOYEE — ACCEPT ORDER
# ═════════════════════════════════════════════

class AcceptOrderView(APIView):
    """
    POST /checkout/orders/{order_id}/accept/

    Rules:
    - Stripe orders: payment must be PAID
    - Cash orders:   payment must be PAID (employee clicked "Receive Cash" first)
    - Order status must be ORDER_SENT

    Transitions order to PREPARING.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, order_id):
        order = _order_or_404(order_id)
        if not order:
            return APIResponse.error(message="Order not found.", status_code=404)
        if not _can_manage(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)
        if order.status != Order.Status.ORDER_SENT:
            return APIResponse.error(message="Only ORDER_SENT orders can be accepted.", status_code=400)

        payment = order.payment
        if not payment or payment.status != Payment.Status.PAID:
            return APIResponse.error(
                message="Payment not confirmed. For cash orders, click 'Receive Cash' first.",
                status_code=400,
            )

        s = AcceptOrderSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        now = timezone.now()
        order.status       = Order.Status.PREPARING
        order.preparing_at = now
        # Optionally store prep_time in pickup_time if provided
        if s.validated_data.get("prep_time"):
            order.pickup_time = f"{s.validated_data['prep_time']} minutes"
        order.save(update_fields=["status", "preparing_at", "pickup_time", "updated_at"])

        return APIResponse.success(
            message="Order accepted. Preparation started.",
            data=OrderSerializer(order).data,
        )


# ═════════════════════════════════════════════
#  EMPLOYEE — UPDATE STATUS  (PREPARING → READY)
# ═════════════════════════════════════════════

class UpdateOrderStatusView(APIView):
    """
    POST /checkout/orders/{order_id}/update-status/

    Allowed transition: PREPARING → READY
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, order_id):
        order = _order_or_404(order_id)
        if not order:
            return APIResponse.error(message="Order not found.", status_code=404)
        if not _can_manage(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        transitions = {
            Order.Status.PREPARING: Order.Status.READY,
        }
        next_status = transitions.get(order.status)
        if not next_status:
            return APIResponse.error(
                message=f"Cannot advance from '{order.status}'. "
                        f"Only PREPARING → READY is allowed via this endpoint.",
                status_code=400,
            )

        now = timezone.now()
        order.status = next_status
        if next_status == Order.Status.READY:
            order.ready_at = now
        order.save(update_fields=["status", "ready_at", "updated_at"])

        return APIResponse.success(
            message=f"Order status updated to '{next_status}'.",
            data=OrderSerializer(order).data,
        )


# ═════════════════════════════════════════════
#  EMPLOYEE — CANCEL ORDER
# ═════════════════════════════════════════════

class CancelOrderView(APIView):
    """
    POST /checkout/orders/{order_id}/cancel/

    Customer can cancel if ORDER_SENT.
    Employee/owner/admin can cancel if ORDER_SENT or PREPARING.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, order_id):
        user = request.user

        if user.role == "customer":
            order = _order_or_404(order_id, extra_filter={"customer": user})
        else:
            order = _order_or_404(order_id)

        if not order:
            return APIResponse.error(message="Order not found.", status_code=404)

        if user.role == "customer":
            if order.status != Order.Status.ORDER_SENT:
                return APIResponse.error(
                    message="You can only cancel a pending order (ORDER_SENT).",
                    status_code=400,
                )
        else:
            if not _can_manage(user, order):
                return APIResponse.error(message="Unauthorized.", status_code=403)
            if order.status not in (Order.Status.ORDER_SENT, Order.Status.PREPARING):
                return APIResponse.error(
                    message="Order cannot be cancelled at this stage.",
                    status_code=400,
                )

        s = CancelOrderSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        reason = s.validated_data.get("reason", "")
        order.status       = Order.Status.CANCELLED
        order.cancelled_at = timezone.now()
        if reason:
            order.note = f"[Cancelled]: {reason}"
        order.save(update_fields=["status", "cancelled_at", "note", "updated_at"])

        return APIResponse.success(message="Order cancelled.")


# ═════════════════════════════════════════════
#  USER — MARK ARRIVED  (triggers Celery)
# ═════════════════════════════════════════════

class MarkArrivedView(APIView):
    """
    POST /checkout/orders/{order_id}/arrived/

    Customer taps "I Arrived".
    Dispatches Celery task to set user_arrived = True on the order.
    Employee sees the flag in the order detail endpoint.
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def post(self, request, order_id):
        s = MarkArrivedSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        order = Order.objects.filter(
            id=order_id,
            customer=request.user,
            status__in=[Order.Status.ORDER_SENT, Order.Status.PREPARING, Order.Status.READY],
        ).first()
        if not order:
            return APIResponse.error(message="Order not found or already completed.", status_code=404)

        if order.user_arrived:
            return APIResponse.error(message="Arrival already recorded.", status_code=400)

        # Fire Celery task
        mark_user_arrived.delay(
            order_id=str(order_id),
            latitude=float(s.validated_data["latitude"])  if s.validated_data.get("latitude")  else None,
            longitude=float(s.validated_data["longitude"]) if s.validated_data.get("longitude") else None,
        )

        return APIResponse.success(message="Arrival noted. The restaurant has been informed.")


# ═════════════════════════════════════════════
#  EMPLOYEE — VIEW DISTANCE / ETA
# ═════════════════════════════════════════════

class OrderETAView(APIView):
    """
    GET /checkout/orders/{order_id}/eta/

    Returns:
      - user_arrived flag
      - distance_km  (if coords available)
      - eta_minutes  (mocked: distance / AVG_SPEED_KMH * 60)
      - remaining_minutes (pickup_time parsing if it's a digit string)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        order = _order_or_404(order_id)
        if not order:
            return APIResponse.error(message="Order not found.", status_code=404)
        if not _can_manage(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        branch_lat = order.branch.latitude  if order.branch else None
        branch_lon = order.branch.longitude if order.branch else None
        distance   = _haversine_km(order.arrived_lat, order.arrived_lon, branch_lat, branch_lon)
        eta        = round(distance / AVG_SPEED_KMH * 60, 1) if distance is not None else None

        # remaining_minutes: only if pickup_time is purely numeric (minutes)
        remaining = None
        if order.pickup_time:
            parts = order.pickup_time.strip().split()
            try:
                remaining = int(parts[0])
            except (ValueError, IndexError):
                remaining = None

        data = {
            "order_id":          str(order.id),
            "user_arrived":      order.user_arrived,
            "distance_km":       distance,
            "eta_minutes":       eta,
            "remaining_minutes": remaining,
            "arrived_lat":       order.arrived_lat,
            "arrived_lon":       order.arrived_lon,
        }
        s = OrderETASerializer(data=data)
        s.is_valid()   # always valid — computed data
        return APIResponse.success(data=s.data)


# ═════════════════════════════════════════════
#  DELIVERY — QR SCAN  (employee scans)
# ═════════════════════════════════════════════

class DeliverByQRView(APIView):
    """
    POST /checkout/orders/deliver-qr/

    Employee scans the customer's QR code.
    Marks order DELIVERED and invalidates the token.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        s = QRScanSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        order = (
            Order.objects
            .select_related("branch", "branch__restaurant", "car", "payment")
            .filter(qr_token=s.validated_data["qr_token"], status=Order.Status.READY)
            .first()
        )
        if not order:
            return APIResponse.error(message="Invalid QR code or order not ready.", status_code=404)
        if not _can_manage(request.user, order):
            return APIResponse.error(message="Unauthorized.", status_code=403)

        order.status       = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
        order.qr_token     = None   # invalidate token
        order.save(update_fields=["status", "delivered_at", "qr_token", "updated_at"])

        return APIResponse.success(
            message="QR scanned. Order delivered!",
            data={
                "order_number": order.order_number,
                "delivered_at": str(order.delivered_at),
            },
        )


# ═════════════════════════════════════════════
#  DELIVERY — CUSTOMER SELF-CONFIRM
# ═════════════════════════════════════════════

class DeliverManualView(APIView):
    """
    POST /checkout/orders/{order_id}/confirm-delivery/

    Customer taps "I received my order".
    Order must be READY.
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    @transaction.atomic
    def post(self, request, order_id):
        order = Order.objects.filter(
            id=order_id,
            customer=request.user,
            status=Order.Status.READY,
        ).first()
        if not order:
            return APIResponse.error(message="Order not found or not ready.", status_code=404)

        order.status       = Order.Status.DELIVERED
        order.delivered_at = timezone.now()
        order.save(update_fields=["status", "delivered_at", "updated_at"])

        return APIResponse.success(
            message="Order confirmed as delivered. Enjoy!",
            data=OrderSerializer(order).data,
        )


# ═════════════════════════════════════════════
#  CUSTOMER — GET QR TOKEN
# ═════════════════════════════════════════════

class OrderQRView(APIView):
    """
    GET /checkout/orders/{order_id}/qr/

    Returns the QR token for the customer to display.
    Only available when order status is READY.
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request, order_id):
        order = Order.objects.filter(
            id=order_id,
            customer=request.user,
            status=Order.Status.READY,
        ).first()
        if not order:
            return APIResponse.error(message="Order not found or not ready.", status_code=404)

        return APIResponse.success(
            data={
                "order_number": order.order_number,
                "qr_token":     order.qr_token,
            }
        )


# ═════════════════════════════════════════════
#  FEEDBACK
# ═════════════════════════════════════════════

class FeedbackView(APIView):
    """
    POST /checkout/orders/{order_id}/feedback/
    GET  /checkout/orders/{order_id}/feedback/  — view submitted feedback
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request, order_id):
        order = Order.objects.filter(id=order_id, customer=request.user).first()
        if not order:
            return APIResponse.error(message="Order not found.", status_code=404)
        feedback = getattr(order, "feedback", None)
        if not feedback:
            return APIResponse.error(message="No feedback submitted yet.", status_code=404)
        return APIResponse.success(data=FeedbackSerializer(feedback).data)

    def post(self, request, order_id):
        order = Order.objects.filter(
            id=order_id,
            customer=request.user,
            status=Order.Status.DELIVERED,
        ).first()
        if not order:
            return APIResponse.error(message="Order not found or not delivered yet.", status_code=404)
        if hasattr(order, "feedback"):
            return APIResponse.error(message="Feedback already submitted.", status_code=400)

        s = FeedbackSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        feedback = s.save(order=order, customer=request.user)
        return APIResponse.success(
            message="Thank you for your feedback!",
            data=FeedbackSerializer(feedback).data,
            status_code=201,
        )
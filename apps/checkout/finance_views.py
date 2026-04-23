from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Avg
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.utils.custom_response import APIResponse
from apps.authentication.permissions import IsOwner, IsAdmin, IsCustomer
from apps.restaurants.models import Restaurant

from .models import (
    Order,
    Payment,
    CommissionSettings,
    RestaurantCommission,
    OwnerWallet,
    CommissionTransaction,
    PayoutRequest,
    SupportTicket,
)
from .finance_serializers import (
    CommissionSettingsSerializer,
    CustomRateWriteSerializer,
    CustomRateListSerializer,
    CommissionTransactionSerializer,
    PayoutRequestSerializer,
    PayoutActionSerializer,
    SupportTicketSerializer,
    SupportTicketCreateSerializer,
    SupportTicketReplySerializer,
    AdminDashboardSerializer,
    OwnerDashboardSerializer,
    OwnerWalletStatsSerializer,
)


# --- SHARED HELPER — apply commission on payment -------------------------------------------------------------------------------------------------------


def _apply_commission(order: Order):
    """
    Called when payment becomes PAID.
    - Always deducts commission from owner wallet.
    - Only Stripe credits subtotal to wallet (cash owner collects physically).
    - Records CommissionTransaction for audit.
    """
    restaurant = order.branch.restaurant if order.branch else None
    if not restaurant:
        return

    try:
        rate = restaurant.commission  # custom override
    except RestaurantCommission.DoesNotExist:
        rate = CommissionSettings.get()  # global default

    commission = rate.calculate(order.subtotal)
    wallet, _ = OwnerWallet.objects.get_or_create(owner=restaurant.owner)

    with transaction.atomic():
        wallet.balance -= commission
        if order.payment and order.payment.method == Payment.Method.STRIPE:
            wallet.balance += order.subtotal
        wallet.save(update_fields=["balance", "updated_at"])

        CommissionTransaction.objects.get_or_create(
            order=order,
            defaults={
                "restaurant": restaurant,
                "subtotal": order.subtotal,
                "commission_amount": commission,
                "status": CommissionTransaction.Status.COMPLETED,
            },
        )


# --- PRIVATE HELPERS -------------------------------------------------------------------------------------------------------


def _order_stats(qs, today, yesterday):
    t_count = qs.filter(created_at__date=today).count()
    y_count = qs.filter(created_at__date=yesterday).count()
    t_revenue = qs.filter(created_at__date=today).aggregate(r=Sum("subtotal"))[
        "r"
    ] or Decimal("0")
    y_revenue = qs.filter(created_at__date=yesterday).aggregate(r=Sum("subtotal"))[
        "r"
    ] or Decimal("0")

    def pct(new, old):
        if old == 0:
            return 100.0 if new > 0 else 0.0
        return round(float((new - old) / old * 100), 1)

    return {
        "today_orders": t_count,
        "order_change_pct": pct(t_count, y_count),
        "today_revenue": t_revenue,
        "revenue_change_pct": pct(t_revenue, y_revenue),
    }


def _seven_day_trend(qs, field="subtotal"):
    return [
        {
            "day": (timezone.now() - timedelta(days=i)).strftime("%a"),
            "value": float(
                qs.filter(
                    created_at__date=(timezone.now() - timedelta(days=i)).date()
                ).aggregate(v=Sum(field))["v"]
                or 0
            ),
        }
        for i in range(6, -1, -1)
    ]


def _paginate(request, qs, serializer_class):
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))
    except (ValueError, TypeError):
        page, page_size = 1, 20
    total = qs.count()
    start = (page - 1) * page_size
    return APIResponse.success(
        data=serializer_class(qs[start : start + page_size], many=True).data,
        meta={
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, -(-total // page_size)),
        },
    )


# --- ADMIN DASHBOARD -------------------------------------------------------------------------------------------------------


class AdminDashboardView(APIView):
    """GET /api/v1/admin/dashboard/"""

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        delivered = Order.objects.filter(status=Order.Status.DELIVERED)
        stats = _order_stats(delivered, today, yesterday)

        avg_time = None
        timed = list(
            Order.objects.filter(
                status=Order.Status.DELIVERED,
                preparing_at__isnull=False,
                delivered_at__isnull=False,
            )[:200]
        )
        if timed:
            avg_time = round(
                sum(
                    (o.delivered_at - o.preparing_at).total_seconds() / 60
                    for o in timed
                )
                / len(timed),
                1,
            )

        total_commission = CommissionTransaction.objects.filter(
            status=CommissionTransaction.Status.COMPLETED
        ).aggregate(t=Sum("commission_amount"))["t"] or Decimal("0")

        recent = Order.objects.select_related("customer").order_by("-created_at")[:5]

        data = {
            **stats,
            "avg_delivery_minutes": avg_time,
            "commission_balance": total_commission,
            "revenue_trend": _seven_day_trend(delivered),
            "recent_orders": [
                {
                    "order_number": o.order_number,
                    "customer": o.customer.full_name if o.customer else "",
                    "total": str(o.total),
                    "status": o.status,
                }
                for o in recent
            ],
        }

        s = AdminDashboardSerializer(data=data)
        s.is_valid()
        return APIResponse.success(data=s.data)


# --- OWNER DASHBOARD -------------------------------------------------------------------------------------------------------


class OwnerDashboardView(APIView):
    """GET /api/v1/owner/dashboard/"""

    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)

        restaurant = Restaurant.objects.filter(owner=request.user).first()
        if not restaurant:
            return APIResponse.error(message="Restaurant not found.", status_code=404)

        orders = Order.objects.filter(branch__restaurant=restaurant)
        stats = _order_stats(orders, today, yesterday)

        data = {
            **stats,
            "active_branches": restaurant.branches.filter(is_active=True).count(),
            "pending_approvals": restaurant.branches.filter(is_active=False).count(),
            "total_customers": orders.filter(customer__isnull=False)
            .values("customer")
            .distinct()
            .count(),
            "pending_tickets": SupportTicket.objects.filter(
                order__branch__restaurant=restaurant,
                status=SupportTicket.Status.OPEN,
            ).count(),
            "order_overview": _seven_day_trend(orders),
            "revenue_trend": _seven_day_trend(
                orders.filter(status=Order.Status.DELIVERED)
            ),
        }

        s = OwnerDashboardSerializer(data=data)
        s.is_valid()
        return APIResponse.success(data=s.data)


# --- OWNER WALLET -------------------------------------------------------------------------------------------------------


class OwnerWalletView(APIView):
    """GET /api/v1/owner/wallet/"""

    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        today = timezone.now().date()
        this_month = today.replace(day=1)
        last_month_end = this_month - timedelta(days=1)
        last_month = last_month_end.replace(day=1)

        restaurant = Restaurant.objects.filter(owner=request.user).first()
        if not restaurant:
            return APIResponse.error(message="Restaurant not found.", status_code=404)

        orders = Order.objects.filter(branch__restaurant=restaurant)

        def month_agg(start, end):
            qs = orders.filter(created_at__date__gte=start, created_at__date__lte=end)
            sales = qs.aggregate(s=Sum("subtotal"))["s"] or Decimal("0")
            count = qs.count()
            avg = qs.aggregate(a=Avg("subtotal"))["a"] or Decimal("0")
            return sales, count, avg

        this_sales, this_count, this_avg = month_agg(this_month, today)
        last_sales, last_count, last_avg = month_agg(last_month, last_month_end)

        def pct(new, old):
            if old == 0:
                return 100.0 if new > 0 else 0.0
            return round(float((new - old) / old * 100), 1)

        wallet, _ = OwnerWallet.objects.get_or_create(owner=request.user)

        data = {
            "wallet_balance": wallet.balance,
            "total_sales": this_sales,
            "sales_change_pct": pct(this_sales, last_sales),
            "total_orders": this_count,
            "orders_change_pct": pct(this_count, last_count),
            "avg_order_value": this_avg.quantize(Decimal("0.01")),
            "avg_order_change_pct": pct(this_avg, last_avg),
            "revenue_trend": _seven_day_trend(
                orders.filter(status=Order.Status.DELIVERED)
            ),
            "order_volume": _seven_day_trend(orders),
        }

        s = OwnerWalletStatsSerializer(data=data)
        s.is_valid()
        return APIResponse.success(data=s.data)


# --- PAYOUT -------------------------------------------------------------------------------------------------------


class PayoutRequestView(APIView):
    """
    GET  /api/v1/owner/payout/
    POST /api/v1/owner/payout/
    """

    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        qs = PayoutRequest.objects.filter(owner=request.user)
        return APIResponse.success(
            data=PayoutRequestSerializer(qs, many=True).data,
            meta={"count": qs.count()},
        )

    def post(self, request):
        s = PayoutRequestSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        wallet, _ = OwnerWallet.objects.get_or_create(owner=request.user)
        if s.validated_data["amount"] > wallet.balance:
            return APIResponse.error(
                message=f"Insufficient balance. Available: {wallet.balance} SAR.",
                status_code=400,
            )

        payout = s.save(owner=request.user)
        return APIResponse.success(
            message="Payout request submitted.",
            data=PayoutRequestSerializer(payout).data,
            status_code=201,
        )


class AdminPayoutListView(APIView):
    """GET /api/v1/admin/payouts/"""

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = PayoutRequest.objects.select_related("owner").order_by("-created_at")
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return _paginate(request, qs, PayoutRequestSerializer)


class AdminPayoutActionView(APIView):
    """POST /api/v1/admin/payouts/{pk}/action/"""

    permission_classes = [IsAuthenticated, IsAdmin]

    @transaction.atomic
    def post(self, request, pk):
        try:
            payout = PayoutRequest.objects.select_related("owner").get(id=pk)
        except PayoutRequest.DoesNotExist:
            return APIResponse.error(
                message="Payout request not found.", status_code=404
            )

        if payout.status != PayoutRequest.Status.PENDING:
            return APIResponse.error(
                message="Payout already actioned.", status_code=400
            )

        s = PayoutActionSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        if d["action"] == "accept":
            wallet, _ = OwnerWallet.objects.get_or_create(owner=payout.owner)
            wallet.balance -= payout.amount
            wallet.save(update_fields=["balance", "updated_at"])
            payout.status = PayoutRequest.Status.COMPLETED
        else:
            payout.status = PayoutRequest.Status.REJECTED
            payout.rejection_reason = d.get("reason", "")

        payout.actioned_by = request.user
        payout.actioned_at = timezone.now()
        payout.save(
            update_fields=[
                "status",
                "rejection_reason",
                "actioned_by",
                "actioned_at",
                "updated_at",
            ]
        )

        msg = (
            "Payout accepted."
            if payout.status == PayoutRequest.Status.COMPLETED
            else "Payout rejected."
        )
        return APIResponse.success(
            message=msg, data=PayoutRequestSerializer(payout).data
        )


# --- COMMISSION SETTINGS -------------------------------------------------------------------------------------------------------


class AdminCommissionSettingsView(APIView):
    """
    GET   /api/v1/admin/commission/settings/
    PATCH /api/v1/admin/commission/settings/
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        return APIResponse.success(
            data=CommissionSettingsSerializer(CommissionSettings.get()).data
        )

    def patch(self, request):
        s = CommissionSettingsSerializer(
            CommissionSettings.get(), data=request.data, partial=True
        )
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        s.save()
        return APIResponse.success(message="Commission settings updated.", data=s.data)


class AdminCommissionCustomRatesView(APIView):
    """
    GET  /api/v1/admin/commission/custom-rates/
    POST /api/v1/admin/commission/custom-rates/
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        restaurants = Restaurant.objects.select_related("commission").order_by(
            "brand_name"
        )
        global_s = CommissionSettings.get()
        if request.query_params.get("search"):
            restaurants = restaurants.filter(
                brand_name__icontains=request.query_params["search"]
            )

        rows = []
        for r in restaurants:
            try:
                c = r.commission
                is_custom = True
                pct, fixed = c.percentage, c.fixed_sar
            except RestaurantCommission.DoesNotExist:
                is_custom = False
                pct, fixed = global_s.percentage, global_s.fixed_sar

            rows.append(
                {
                    "restaurant_id": r.id,
                    "restaurant_name": r.brand_name,
                    "percentage": pct,
                    "fixed_sar": fixed,
                    "is_custom": is_custom,
                }
            )

        s = CustomRateListSerializer(rows, many=True)
        return APIResponse.success(data=s.data, meta={"count": len(rows)})

    def post(self, request):
        s = CustomRateWriteSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        try:
            restaurant = Restaurant.objects.get(id=d["restaurant_id"])
        except Restaurant.DoesNotExist:
            return APIResponse.error(message="Restaurant not found.", status_code=404)

        obj, _ = RestaurantCommission.objects.get_or_create(restaurant=restaurant)
        for f in ["percentage", "percentage_active", "fixed_sar", "fixed_active"]:
            if f in d:
                setattr(obj, f, d[f])
        obj.save()

        from .finance_serializers import RestaurantCommissionSerializer

        return APIResponse.success(
            message="Custom rate saved.",
            data=RestaurantCommissionSerializer(obj).data,
        )


class AdminCommissionTransactionsView(APIView):
    """GET /api/v1/admin/commission/transactions/"""

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = CommissionTransaction.objects.select_related("restaurant", "order")
        if request.query_params.get("date"):
            qs = qs.filter(created_at__date=request.query_params["date"])
        return _paginate(request, qs, CommissionTransactionSerializer)


# --- SUPPORT TICKETS -------------------------------------------------------------------------------------------------------


class SupportTicketView(APIView):
    """
    POST /api/v1/support/tickets/
    GET  /api/v1/support/tickets/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == "admin":
            qs = SupportTicket.objects.select_related("customer", "order")
        elif user.role == "customer":
            qs = SupportTicket.objects.filter(customer=user)
        else:
            return APIResponse.error(message="Unauthorized.", status_code=403)

        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])

        return _paginate(request, qs.order_by("-created_at"), SupportTicketSerializer)

    def post(self, request):
        if request.user.role != "customer":
            return APIResponse.error(
                message="Only customers can submit tickets.", status_code=403
            )

        s = SupportTicketCreateSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        order = None
        if d.get("order_id"):
            order = Order.objects.filter(
                id=d["order_id"], customer=request.user
            ).first()
            if not order:
                return APIResponse.error(message="Order not found.", status_code=404)

        ticket = SupportTicket.objects.create(
            customer=request.user,
            order=order,
            full_name=d["full_name"],
            email=d["email"],
            description=d["description"],
        )
        return APIResponse.success(
            message="Support ticket submitted.",
            data=SupportTicketSerializer(ticket).data,
            status_code=201,
        )


class SupportTicketDetailView(APIView):
    """
    GET   /api/v1/support/tickets/{pk}/
    PATCH /api/v1/support/tickets/{pk}/
    """

    permission_classes = [IsAuthenticated]

    def _get_ticket(self, request, pk):
        if request.user.role == "admin":
            return (
                SupportTicket.objects.filter(id=pk)
                .select_related("customer", "order")
                .first()
            )
        if request.user.role == "customer":
            return SupportTicket.objects.filter(id=pk, customer=request.user).first()
        return None

    def get(self, request, pk):
        ticket = self._get_ticket(request, pk)
        if not ticket:
            return APIResponse.error(message="Ticket not found.", status_code=404)
        return APIResponse.success(data=SupportTicketSerializer(ticket).data)

    def patch(self, request, pk):
        if request.user.role != "admin":
            return APIResponse.error(
                message="Only admins can update tickets.", status_code=403
            )

        ticket = SupportTicket.objects.filter(id=pk).first()
        if not ticket:
            return APIResponse.error(message="Ticket not found.", status_code=404)

        s = SupportTicketReplySerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        updated = []
        if d.get("admin_reply"):
            ticket.admin_reply = d["admin_reply"]
            ticket.replied_by = request.user
            ticket.replied_at = timezone.now()
            updated += ["admin_reply", "replied_by", "replied_at"]
        if d.get("status"):
            ticket.status = d["status"]
            updated.append("status")

        if updated:
            ticket.save(update_fields=updated + ["updated_at"])

        return APIResponse.success(
            message="Ticket updated.", data=SupportTicketSerializer(ticket).data
        )

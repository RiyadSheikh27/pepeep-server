from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.utils.custom_response import APIResponse
from apps.authentication.permissions import IsAdmin, IsOwner, IsCustomer
from apps.authentication.models import User
from apps.restaurants.models import Restaurant, Branch
from apps.restaurants.serializers import BranchDetailSerializer

from .models import (
    Order,
    CustomerWallet,
    CustomerWalletTransaction,
    VisibilitySettings,
    AdminManager,
)
from .site_settings_serializer import (
    CustomerWalletSerializer,
    CustomerWalletTransactionSerializer,
    WalletAdjustmentSerializer,
    VisibilitySettingsSerializer,
    AdminManagerSerializer,
    CreateManagerSerializer,
    ChangePasswordSerializer,
    AdminSetPasswordSerializer,
    OwnerDetailAdminSerializer,
    CustomerDetailAdminSerializer,
    CustomerOrderHistorySerializer,
    _abs,
)

#  --- CUSTOMER WALLET — customer views own wallet -----------------------------------------------------------


class CustomerWalletView(APIView):
    """
    GET /api/v1/user/wallet/
    Returns balance + transaction history.
    """

    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request):
        wallet, _ = CustomerWallet.objects.get_or_create(customer=request.user)
        txns = CustomerWalletTransaction.objects.filter(wallet=wallet)

        try:
            page = max(1, int(request.query_params.get("page", 1)))
            page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))
        except (ValueError, TypeError):
            page, page_size = 1, 20

        total = txns.count()
        start = (page - 1) * page_size

        return APIResponse.success(
            data={
                "balance": str(wallet.balance),
                "transactions": CustomerWalletTransactionSerializer(
                    txns[start : start + page_size], many=True
                ).data,
            },
            meta={
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": max(1, -(-total // page_size)),
            },
        )


#  --- CUSTOMER WALLET — admin adjustments -----------------------------------------------------------

class AdminCustomerWalletView(APIView):
    """
    GET   /api/v1/admin/customers/{pk}/wallet/   — balance + transactions
    POST  /api/v1/admin/customers/{pk}/wallet/   — credit / debit / bonus
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def _get_customer(self, pk):
        return User.objects.filter(id=pk, role="customer").first()

    def get(self, request, pk):
        customer = self._get_customer(pk)
        if not customer:
            return APIResponse.error(message="Customer not found.", status_code=404)

        wallet, _ = CustomerWallet.objects.get_or_create(customer=customer)
        txns = CustomerWalletTransaction.objects.filter(wallet=wallet)

        return APIResponse.success(
            data={
                "customer": customer.full_name,
                "balance": str(wallet.balance),
                "transactions": CustomerWalletTransactionSerializer(
                    txns[:50], many=True
                ).data,
            }
        )

    @transaction.atomic
    def post(self, request, pk):
        customer = self._get_customer(pk)
        if not customer:
            return APIResponse.error(message="Customer not found.", status_code=404)

        s = WalletAdjustmentSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        wallet, _ = CustomerWallet.objects.get_or_create(customer=customer)

        if d["tx_type"] == "debit" and d["amount"] > wallet.balance:
            return APIResponse.error(
                message=f"Insufficient balance. Available: {wallet.balance} SAR.",
                status_code=400,
            )

        if d["tx_type"] in ("credit", "bonus"):
            wallet.balance += d["amount"]
        else:  # debit
            wallet.balance -= d["amount"]

        wallet.save(update_fields=["balance", "updated_at"])

        CustomerWalletTransaction.objects.create(
            wallet=wallet,
            tx_type=d["tx_type"],
            amount=d["amount"],
            reason=d["reason"],
            actioned_by=request.user,
        )

        return APIResponse.success(
            message=f"Wallet {d['tx_type']} of {d['amount']} SAR applied.",
            data={"balance": str(wallet.balance)},
        )


#  --- VISIBILITY SETTINGS ---------------------------------------------------------------------------

class VisibilitySettingsView(APIView):
    """
    GET   /api/v1/admin/visibility/
    PATCH /api/v1/admin/visibility/
    Body: { "radius_km": 10 }
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        s = VisibilitySettingsSerializer(VisibilitySettings.get())
        return APIResponse.success(data=s.data)

    def patch(self, request):
        s = VisibilitySettingsSerializer(
            VisibilitySettings.get(), data=request.data, partial=True
        )
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        s.save()
        return APIResponse.success(message="Visibility settings updated.", data=s.data)


#  --- ADMIN MANAGER ---------------------------------------------------------------------------

class AdminManagerListCreateView(APIView):
    """
    GET  /api/v1/admin/managers/
    POST /api/v1/admin/managers/
    Only super admin (no manager_profile) can access.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def _is_super_admin(self, user):
        return not hasattr(user, "manager_profile")

    def get(self, request):
        if not self._is_super_admin(request.user):
            return APIResponse.error(
                message="Super admin access required.", status_code=403
            )
        managers = AdminManager.objects.select_related("user").order_by("-created_at")
        return APIResponse.success(
            data=AdminManagerSerializer(managers, many=True).data,
            meta={"count": managers.count()},
        )

    def post(self, request):
        if not self._is_super_admin(request.user):
            return APIResponse.error(
                message="Super admin access required.", status_code=403
            )

        s = CreateManagerSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        if User.objects.filter(phone=d["phone"]).exists():
            return APIResponse.error(errors={"phone": ["Phone already in use."]})
        if User.objects.filter(email=d["email"]).exists():
            return APIResponse.error(errors={"email": ["Email already in use."]})

        with transaction.atomic():
            user = User.objects.create_user(
                phone=d["phone"],
                email=d["email"],
                full_name=d["full_name"],
                password=d["password"],
                role="admin",
                is_active=True,
            )
            manager = AdminManager.objects.create(
                user=user,
                access_level=d["access_level"],
                created_by=request.user,
            )

        return APIResponse.success(
            message="Manager created.",
            data=AdminManagerSerializer(manager).data,
            status_code=201,
        )


class AdminManagerDetailView(APIView):
    """
    GET    /api/v1/admin/managers/{pk}/
    PATCH  /api/v1/admin/managers/{pk}/   — change access_level / is_active
    DELETE /api/v1/admin/managers/{pk}/
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def _is_super_admin(self, user):
        return not hasattr(user, "manager_profile")

    def _get(self, pk):
        return AdminManager.objects.filter(id=pk).select_related("user").first()

    def get(self, request, pk):
        if not self._is_super_admin(request.user):
            return APIResponse.error(
                message="Super admin access required.", status_code=403
            )
        manager = self._get(pk)
        if not manager:
            return APIResponse.error(message="Manager not found.", status_code=404)
        return APIResponse.success(data=AdminManagerSerializer(manager).data)

    def patch(self, request, pk):
        if not self._is_super_admin(request.user):
            return APIResponse.error(
                message="Super admin access required.", status_code=403
            )
        manager = self._get(pk)
        if not manager:
            return APIResponse.error(message="Manager not found.", status_code=404)

        if "access_level" in request.data:
            if request.data["access_level"] not in ("limited", "full"):
                return APIResponse.error(
                    errors={"access_level": ["Must be 'limited' or 'full'."]}
                )
            manager.access_level = request.data["access_level"]
            manager.save(update_fields=["access_level", "updated_at"])

        if "is_active" in request.data:
            manager.user.is_active = bool(request.data["is_active"])
            manager.user.save(update_fields=["is_active", "updated_at"])

        return APIResponse.success(
            message="Manager updated.", data=AdminManagerSerializer(manager).data
        )

    def delete(self, request, pk):
        if not self._is_super_admin(request.user):
            return APIResponse.error(
                message="Super admin access required.", status_code=403
            )
        manager = self._get(pk)
        if not manager:
            return APIResponse.error(message="Manager not found.", status_code=404)
        manager.user.delete()
        return APIResponse.success(message="Manager deleted.")


#  --- CHANGE PASSWORD  (owner / admin / manager) -----------------------------------------------------------

class ChangePasswordView(APIView):
    """
    POST /api/v1/auth/change-password/
    Roles: owner, admin (including managers)
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role not in ("owner", "admin"):
            return APIResponse.error(
                message="Not allowed for this role.", status_code=403
            )

        s = ChangePasswordSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data

        if not request.user.check_password(d["old_password"]):
            return APIResponse.error(errors={"old_password": ["Incorrect password."]})

        request.user.set_password(d["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        return APIResponse.success(message="Password changed successfully.")


class AdminSetEmployeePasswordView(APIView):
    """
    POST /api/v1/owner/staff/{pk}/set-password/
    Owner or admin sets employee password directly (no old password needed).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.user.role not in ("owner", "admin"):
            return APIResponse.error(message="Not allowed.", status_code=403)

        from apps.restaurants.models import Employee

        try:
            if request.user.role == "owner":
                emp = Employee.objects.select_related("user").get(
                    id=pk, branch__restaurant__owner=request.user
                )
            else:
                emp = Employee.objects.select_related("user").get(id=pk)
        except Employee.DoesNotExist:
            return APIResponse.error(message="Employee not found.", status_code=404)

        s = AdminSetPasswordSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        emp.user.set_password(s.validated_data["new_password"])
        emp.user.save(update_fields=["password", "updated_at"])
        return APIResponse.success(message="Employee password updated.")


#  --- FIXED ADMIN — OWNER DETAIL  (with docs + branches)

class AdminOwnerDetailFixedView(APIView):
    """
    GET    /api/v1/admin/owners/{pk}/
    PATCH  /api/v1/admin/owners/{pk}/   — activate / deactivate
    DELETE /api/v1/admin/owners/{pk}/
    Replaces existing AdminOwnerDetailView.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def _get_owner(self, pk):
        return User.objects.filter(id=pk, role="owner").first()

    def get(self, request, pk):
        owner = self._get_owner(pk)
        if not owner:
            return APIResponse.error(message="Owner not found.", status_code=404)

        restaurant = (
            Restaurant.objects.filter(owner=owner)
            .prefetch_related("branches__opening_hours")
            .first()
        )

        branches = []
        if restaurant:
            from .site_settings_serializer import BranchDetailAdminSerializer

            branches = BranchDetailAdminSerializer(
                restaurant.branches.all(), many=True
            ).data

        data = {
            "id": owner.id,
            "full_name": owner.full_name,
            "phone": owner.phone,
            "email": owner.email,
            "avatar": _abs(owner.avatar) if owner.avatar else None,
            "is_active": owner.is_active,
            "created_at": owner.created_at,
            "restaurant_id": str(restaurant.id) if restaurant else None,
            "brand_name": restaurant.brand_name if restaurant else None,
            "legal_name": restaurant.legal_name if restaurant else None,
            "logo": _abs(restaurant.logo) if restaurant and restaurant.logo else None,
            "status": restaurant.status if restaurant else None,
            "cr_number": restaurant.cr_number if restaurant else None,
            "vat_number": restaurant.vat_number if restaurant else None,
            "cr_document": (
                _abs(restaurant.cr_document)
                if restaurant and restaurant.cr_document
                else None
            ),
            "vat_certificate": (
                _abs(restaurant.vat_certificate)
                if restaurant and restaurant.vat_certificate
                else None
            ),
            "short_description": restaurant.short_description if restaurant else None,
            "city": restaurant.city if restaurant else None,
            "street_name": restaurant.street_name if restaurant else None,
            "branches": branches,
        }

        return APIResponse.success(data=data)

    def patch(self, request, pk):
        owner = self._get_owner(pk)
        if not owner:
            return APIResponse.error(message="Owner not found.", status_code=404)
        is_active = request.data.get("is_active")
        if is_active is None:
            return APIResponse.error(errors={"is_active": ["This field is required."]})
        owner.is_active = bool(is_active)
        owner.save(update_fields=["is_active", "updated_at"])
        return APIResponse.success(
            message=f"Owner {'activated' if owner.is_active else 'deactivated'}."
        )

    def delete(self, request, pk):
        owner = self._get_owner(pk)
        if not owner:
            return APIResponse.error(message="Owner not found.", status_code=404)
        owner.delete()
        return APIResponse.success(message="Owner and all associated data deleted.")


#  --- FIXED ADMIN — CUSTOMER DETAIL  (with wallet + order history) ---------------------------------------------------------------------------

class AdminCustomerDetailFixedView(APIView):
    """
    GET    /api/v1/admin/customers/{pk}/
    PATCH  /api/v1/admin/customers/{pk}/   — activate / deactivate
    DELETE /api/v1/admin/customers/{pk}/
    Replaces existing AdminCustomerDetailView.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    def _get_customer(self, pk):
        return User.objects.filter(id=pk, role="customer").first()

    def get(self, request, pk):
        customer = self._get_customer(pk)
        if not customer:
            return APIResponse.error(message="Customer not found.", status_code=404)

        wallet, _ = CustomerWallet.objects.get_or_create(customer=customer)
        orders = Order.objects.filter(customer=customer).order_by("-created_at")
        recent_txns = CustomerWalletTransaction.objects.filter(wallet=wallet)[:10]

        data = {
            "id": str(customer.id),
            "full_name": customer.full_name,
            "username": customer.username,
            "phone": customer.phone,
            "email": customer.email,
            "avatar": _abs(customer.avatar) if customer.avatar else None,
            "is_active": customer.is_active,
            "created_at": customer.created_at,
            "total_orders": orders.count(),
            "wallet_balance": wallet.balance,
            "order_history": [
                {
                    "id": str(o.id),
                    "order_number": o.order_number,
                    "status": o.status,
                    "total": str(o.total),
                    "created_at": o.created_at,
                }
                for o in orders[:20]
            ],
            "wallet_transactions": CustomerWalletTransactionSerializer(
                recent_txns, many=True
            ).data,
        }

        return APIResponse.success(data=data)

    def patch(self, request, pk):
        customer = self._get_customer(pk)
        if not customer:
            return APIResponse.error(message="Customer not found.", status_code=404)
        is_active = request.data.get("is_active")
        if is_active is None:
            return APIResponse.error(errors={"is_active": ["This field is required."]})
        customer.is_active = bool(is_active)
        customer.save(update_fields=["is_active", "updated_at"])
        return APIResponse.success(
            message=f"Customer {'activated' if customer.is_active else 'deactivated'}."
        )

    def delete(self, request, pk):
        customer = self._get_customer(pk)
        if not customer:
            return APIResponse.error(message="Customer not found.", status_code=404)
        customer.delete()
        return APIResponse.success(message="Customer deleted.")

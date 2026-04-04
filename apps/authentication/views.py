import json

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from apps.utils.custom_response import APIResponse
from apps.restaurants.models import Branch, Employee
from apps.restaurants.serializers import (
    RestaurantSerializer,
    RestaurantBankDetailSerializer,
    BranchDetailSerializer,
    RestaurantListSerializer,
    BranchListSerializer,
)
from .models import OTPVerification
from .permissions import IsCustomer, IsOwner, IsAdmin
from .serializers import (
    # Customer
    CustomerOTPSendSerializer, CustomerOTPVerifySerializer,
    CustomerProfileSerializer,
    ChangePhoneRequestSerializer, ChangePhoneVerifySerializer,
    # Employee
    EmployeeLoginSerializer, EmployeeDetailSerializer, CreateEmployeeSerializer,
    # Owner — auth & registration
    OwnerLoginSerializer, BranchLoginSerializer,
    BranchCreateSerializer, OwnerRegSubmitSerializer,
    # Owner — profile
    OwnerProfileSerializer, OpeningHoursWriteSerializer,
    # Admin
    AdminLoginSerializer, AdminForgotPasswordSerializer,
    AdminResetPasswordSerializer, AdminProfileSerializer,
    AdminCustomerListSerializer, AdminOwnerListSerializer, AdminEmployeeListSerializer,
)
from .services import (
    OTPService, CustomerAuthService, EmployeeAuthService,
    OwnerAuthService, AdminAuthService,
    AuthError, OTPRateLimited, OTPExpired, OTPInvalid,
    OTPMaxAttempts, InvalidCredentials, InvalidToken, NotFound,
)


# --- Helpers --------------------------------------------------------------

def _handle(exc):
    """Map a service exception to an APIResponse error."""
    return APIResponse.error(
        errors={"detail": [str(exc)]},
        message=str(exc),
        status_code=getattr(exc, "status_code", 400),
    )


def _paginate(request, qs, serializer_class):
    """
    Applies page-based pagination to any queryset and returns an APIResponse.
    Query params: page (default 1), page_size (default 20, max 100).
    """
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))
    except (ValueError, TypeError):
        page, page_size = 1, 20

    total = qs.count()
    start = (page - 1) * page_size
    end = start + page_size
    data = serializer_class(qs[start:end], many=True).data

    return APIResponse.success(
        data=data,
        meta={
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, -(-total // page_size)),
        },
    )


def _paginate_list(request, items: list, serializer_class):
    """
    Same as _paginate but works on a plain Python list (e.g. pre-annotated results).
    """
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, max(1, int(request.query_params.get("page_size", 20))))
    except (ValueError, TypeError):
        page, page_size = 1, 20

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    data = serializer_class(items[start:end], many=True).data

    return APIResponse.success(
        data=data,
        meta={
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, -(-total // page_size)),
        },
    )


def _parse_branches(request) -> tuple[list | None, "APIResponse | None"]:
    """
    Parse and validate the 'branches' JSON string field from multipart form data.
    Returns (validated_branches, None) on success or (None, error_response) on failure.
    """
    raw = request.data.get("branches", "")
    try:
        raw_branches = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, APIResponse.error(
            errors={"branches": ["Must be a valid JSON string."]},
            message="Invalid branch data.",
        )

    if not isinstance(raw_branches, list) or not raw_branches:
        return None, APIResponse.error(
            errors={"branches": ["Must be a non-empty JSON array."]},
            message="Invalid branch data.",
        )

    validated = []
    for i, branch_data in enumerate(raw_branches):
        s = BranchCreateSerializer(data=branch_data)
        if not s.is_valid():
            return None, APIResponse.error(
                errors={f"branches[{i}]": s.errors},
                message=f"Invalid data in branch {i + 1}.",
            )
        validated.append(s.validated_data)

    return validated, None


# --- Customer ------------------------------------------------------------------

class CustomerOTPSendView(APIView):
    """
    POST /api/v1/customer/auth/otp/send/
    Body: { phone, purpose }  purpose: "login" | "change_phone"
    """
    permission_classes = [AllowAny]

    def post(self, request):
        s = CustomerOTPSendSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            OTPService.send(s.validated_data["phone"], s.validated_data["purpose"])
        except (OTPRateLimited, AuthError) as e:
            return _handle(e)
        return APIResponse.success(
            message="OTP sent. Valid for 5 minutes.",
            data={"phone": s.validated_data["phone"]},
        )


class CustomerLoginView(APIView):
    """
    POST /api/v1/customer/auth/login/
    Body: { phone, otp_code }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        s = CustomerOTPVerifySerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            user, tokens, is_new = CustomerAuthService.login_or_create(
                s.validated_data["phone"], s.validated_data["otp_code"]
            )
        except (OTPExpired, OTPInvalid, OTPMaxAttempts, InvalidCredentials, AuthError) as e:
            return _handle(e)
        return APIResponse.success(
            message="Welcome! Profile created." if is_new else "Logged in successfully.",
            data={
                "user": {
                    "id":          str(user.id),
                    "full_name":   user.full_name,
                    "phone":       user.phone,
                    "is_new_user": is_new,
                },
                "tokens": tokens,
            },
        )


class CustomerProfileView(APIView):
    """
    GET   /api/v1/customer/profile/
    PATCH /api/v1/customer/profile/
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def get(self, request):
        return APIResponse.success(data=CustomerProfileSerializer(request.user).data)

    def patch(self, request):
        s = CustomerProfileSerializer(request.user, data=request.data, partial=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        s.save()
        return APIResponse.success(message="Profile updated.", data=s.data)


class CustomerChangePhoneRequestView(APIView):
    """
    POST /api/v1/customer/auth/change-phone/request/
    Body: { phone }  ← the new number
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def post(self, request):
        s = ChangePhoneRequestSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            OTPService.send(s.validated_data["phone"], OTPVerification.Purpose.CHANGE_PHONE)
        except (OTPRateLimited, AuthError) as e:
            return _handle(e)
        return APIResponse.success(
            message="OTP sent to the new number.",
            data={"phone": s.validated_data["phone"]},
        )


class CustomerChangePhoneVerifyView(APIView):
    """
    POST /api/v1/customer/auth/change-phone/verify/
    Body: { new_phone, otp_code, phone_verification_token }
    """
    permission_classes = [IsAuthenticated, IsCustomer]

    def post(self, request):
        s = ChangePhoneVerifySerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data
        try:
            otp = OTPService.verify(d["new_phone"], d["otp_code"], OTPVerification.Purpose.CHANGE_PHONE)
            user = CustomerAuthService.change_phone(request.user, d["new_phone"], otp.verification_token)
        except (OTPExpired, OTPInvalid, OTPMaxAttempts, InvalidToken, AuthError) as e:
            return _handle(e)
        return APIResponse.success(
            message="Phone number updated successfully.",
            data={"phone": user.phone},
        )


# --- Employee -------------------------------------------------------------------

class EmployeeLoginView(APIView):
    """
    POST /api/v1/employee/auth/login/
    Body: { username, password }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        s = EmployeeLoginSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            user, tokens = EmployeeAuthService.login(
                s.validated_data["username"], s.validated_data["password"]
            )
        except InvalidCredentials as e:
            return _handle(e)

        emp = user.employee_profile
        return APIResponse.success(
            message="Logged in successfully.",
            data={
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "full_name": user.full_name,
                },
                "branch": {
                    "id": str(emp.branch.id),
                    "name": emp.branch.name,
                    "restaurant_name": emp.branch.restaurant.brand_name,
                },
                "permissions": emp.permissions,
                "tokens": tokens,
            },
        )


# --- Owner — Registration ----------------------------------------------------------------------

class OwnerRegOTPSendView(APIView):
    """
    POST /api/v1/owner/auth/register/otp/send/
    Body: { phone }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone = request.data.get("phone", "").replace(" ", "")
        if not phone:
            return APIResponse.error(errors={"phone": ["This field is required."]})
        try:
            OTPService.send(phone, OTPVerification.Purpose.OWNER_REGISTER)
        except (OTPRateLimited, AuthError) as e:
            return _handle(e)
        return APIResponse.success(message="OTP sent. Valid for 5 minutes.", data={"phone": phone})


class OwnerRegOTPVerifyView(APIView):
    """
    POST /api/v1/owner/auth/register/otp/verify/
    Body: { phone, otp_code }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone = request.data.get("phone", "").replace(" ", "")
        otp_code = request.data.get("otp_code", "")
        if not phone or not otp_code:
            return APIResponse.error(
                errors={"detail": ["phone and otp_code are required."]},
                message="Invalid input.",
            )
        try:
            otp = OTPService.verify(phone, otp_code, OTPVerification.Purpose.OWNER_REGISTER)
        except (OTPExpired, OTPInvalid, OTPMaxAttempts, AuthError) as e:
            return _handle(e)
        return APIResponse.success(
            message="Phone verified.",
            data={"phone_verification_token": otp.verification_token},
        )


class OwnerRegSubmitView(APIView):
    """
    POST /api/v1/owner/auth/register/submit/
    Content-Type: multipart/form-data
    Branches sent as JSON string in 'branches' field.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        s = OwnerRegSubmitSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        branches, err = _parse_branches(request)
        if err:
            return err

        try:
            OwnerAuthService.register(s.validated_data, branches)
        except (InvalidToken, AuthError) as e:
            return _handle(e)

        return APIResponse.success(
            message="Registration submitted successfully. Pending admin approval.",
            status_code=201,
        )


# --- Owner — Login & Branch list (post-login selector) ----------------------------

class OwnerLoginView(APIView):
    """
    POST /api/v1/owner/auth/login/
    Body: { phone, password }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        s = OwnerLoginSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            user, tokens = OwnerAuthService.login(
                s.validated_data["phone"], s.validated_data["password"]
            )
        except InvalidCredentials as e:
            return _handle(e)

        branches = OwnerAuthService.get_active_branches(user)
        return APIResponse.success(
            message="Logged in. Select a branch to continue.",
            data={
                "user": {"id": str(user.id), "full_name": user.full_name},
                "branches": BranchLoginSerializer(branches, many=True).data,
                "tokens": tokens,
            },
        )


class OwnerBranchListView(APIView):
    """
    GET /api/v1/owner/branches/
    Re-fetch active branch list (for branch switching after login).
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        branches = OwnerAuthService.get_active_branches(request.user)
        return APIResponse.success(
            data=BranchLoginSerializer(branches, many=True).data,
            meta={"count": branches.count()},
        )


# --- Owner — Profile (personal info)

class OwnerProfileView(APIView):
    """
    GET /api/v1/owner/profile/ — view personal info
    PATCH /api/v1/owner/profile/ — update full_name, email, avatar
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        return APIResponse.success(data=OwnerProfileSerializer(request.user).data)

    def patch(self, request):
        s = OwnerProfileSerializer(request.user, data=request.data, partial=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        s.save()
        return APIResponse.success(message="Profile updated.", data=s.data)



# --- Owner — Restaurant (brand / legal / address) --------------------------------------

class OwnerRestaurantView(APIView):
    """
    GET   /api/v1/owner/restaurant/   — view restaurant info
    PATCH /api/v1/owner/restaurant/   — update brand, legal, address fields
    Content-Type: multipart/form-data (supports logo, cr_document, vat_certificate)
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        try:
            restaurant = OwnerAuthService.get_restaurant(request.user)
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(data=RestaurantSerializer(restaurant).data)

    def patch(self, request):
        try:
            restaurant = OwnerAuthService.get_restaurant(request.user)
        except NotFound as e:
            return _handle(e)
        s = RestaurantSerializer(restaurant, data=request.data, partial=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        s.save()
        return APIResponse.success(message="Restaurant updated.", data=s.data)


# --- Owner — Bank Detail -----------------------------------------------------

class OwnerBankDetailView(APIView):
    """
    GET /api/v1/owner/restaurant/bank/ — view bank details
    PATCH /api/v1/owner/restaurant/bank/ — update bank details
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        try:
            restaurant = OwnerAuthService.get_restaurant(request.user)
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(data=RestaurantBankDetailSerializer(restaurant.bank_detail).data)

    def patch(self, request):
        try:
            restaurant = OwnerAuthService.get_restaurant(request.user)
        except NotFound as e:
            return _handle(e)
        s = RestaurantBankDetailSerializer(restaurant.bank_detail, data=request.data, partial=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        s.save()
        return APIResponse.success(message="Bank details updated.")



# --- Owner — Branch management (all branches, including inactive) -------------------------------------

class OwnerBranchManageView(APIView):
    """
    GET /api/v1/owner/restaurant/branches/ — list all branches (including inactive)
    POST /api/v1/owner/restaurant/branches/ — add new branch (starts inactive)
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        branches = (
            Branch.objects
            .filter(restaurant__owner=request.user)
            .prefetch_related("opening_hours")
            .order_by("name")
        )
        return APIResponse.success(
            data=BranchDetailSerializer(branches, many=True).data,
            meta={"count": branches.count()},
        )

    def post(self, request):
        s = BranchCreateSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            branch = OwnerAuthService.add_branch(request.user, s.validated_data)
        except (NotFound, AuthError) as e:
            return _handle(e)
        return APIResponse.success(
            message="Branch added. Pending admin approval.",
            data=BranchDetailSerializer(branch).data,
            status_code=201,
        )


class OwnerBranchDetailView(APIView):
    """
    GET /api/v1/owner/restaurant/branches/{id}/ — branch detail
    PATCH /api/v1/owner/restaurant/branches/{id}/ — update name, city, address, min_order
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request, pk):
        try:
            branch = OwnerAuthService.get_branch(request.user, pk)
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(data=BranchDetailSerializer(branch).data)

    def patch(self, request, pk):
        try:
            branch = OwnerAuthService.get_branch(request.user, pk)
        except NotFound as e:
            return _handle(e)
        s = BranchDetailSerializer(branch, data=request.data, partial=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        s.save()
        return APIResponse.success(message="Branch updated.", data=s.data)

    def delete(self, request, pk):
        try:
            OwnerAuthService.delete_branch(request.user, pk)
        except (NotFound, AuthError) as e:
            return _handle(e)
        return APIResponse.success(message="Branch deleted.")


class OwnerBranchOpeningHoursView(APIView):
    """
    PUT /api/v1/owner/restaurant/branches/{id}/opening-hours/
    Replace all opening hours for a branch.
    Body: [ { day, is_open, shifts: [{open, close}] } ]
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def put(self, request, pk):
        if not isinstance(request.data, list):
            return APIResponse.error(
                errors={"detail": ["Payload must be a JSON array of opening hours."]},
                message="Invalid input.",
            )
        s = OpeningHoursWriteSerializer(data=request.data, many=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            branch = OwnerAuthService.set_branch_opening_hours(request.user, pk, s.validated_data)
        except (NotFound, AuthError) as e:
            return _handle(e)
        return APIResponse.success(
            message="Opening hours updated.",
            data=BranchDetailSerializer(branch).data,
        )


# --- Owner — Staff ----------------------------------------------------------------

class OwnerStaffListCreateView(APIView):
    """
    GET /api/v1/owner/staff/ — list all employees
    POST /api/v1/owner/staff/ — create employee account
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        employees = (
            Employee.objects
            .filter(branch__restaurant__owner=request.user)
            .select_related("user", "branch", "branch__restaurant")
            .order_by("branch__name", "user__username")
        )
        return APIResponse.success(
            data=EmployeeDetailSerializer(employees, many=True).data,
            meta={"count": employees.count()},
        )

    def post(self, request):
        s = CreateEmployeeSerializer(data=request.data, context={"request": request})
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        from django.db import transaction
        with transaction.atomic():
            user = request.user.__class__.objects.create_user(
                phone=s.validated_data.get("phone") or None,
                password=s.validated_data["password"],
                username=s.validated_data["username"],
                role="employee",
            )
            branch = Branch.objects.get(id=s.validated_data["branch_id"])
            emp    = Employee.objects.create(
                user=user,
                branch=branch,
                permissions=list(s.validated_data["permissions"]),
                created_by=request.user,
            )

        return APIResponse.success(
            message="Employee account created.",
            data=EmployeeDetailSerializer(emp).data,
            status_code=201,
        )


class OwnerStaffDetailView(APIView):
    """
    GET /api/v1/owner/staff/{id}/
    PATCH /api/v1/owner/staff/{id}/   — update permissions / branch / is_active
    DELETE /api/v1/owner/staff/{id}/   — deactivate employee
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def _get_employee(self, request, pk):
        try:
            return (
                Employee.objects
                .select_related("user", "branch", "branch__restaurant")
                .get(id=pk, branch__restaurant__owner=request.user)
            )
        except Employee.DoesNotExist:
            return None

    def get(self, request, pk):
        emp = self._get_employee(request, pk)
        if not emp:
            return APIResponse.error(message="Employee not found.", status_code=404)
        return APIResponse.success(data=EmployeeDetailSerializer(emp).data)

    def patch(self, request, pk):
        emp = self._get_employee(request, pk)
        if not emp:
            return APIResponse.error(message="Employee not found.", status_code=404)

        permissions = request.data.get("permissions")
        branch_id = request.data.get("branch_id")
        is_active = request.data.get("is_active")

        if permissions is not None:
            invalid = set(permissions) - set(Employee.ALL_PERMISSIONS)
            if invalid:
                return APIResponse.error(errors={"permissions": [f"Invalid permissions: {sorted(invalid)}"]})
            emp.permissions = list(permissions)
            emp.save(update_fields=["permissions", "updated_at"])

        if branch_id is not None:
            try:
                branch = Branch.objects.get(id=branch_id, restaurant__owner=request.user, is_active=True)
                emp.branch = branch
                emp.save(update_fields=["branch", "updated_at"])
            except Branch.DoesNotExist:
                return APIResponse.error(errors={"branch_id": ["Branch not found."]})

        if is_active is not None:
            emp.user.is_active = bool(is_active)
            emp.user.save(update_fields=["is_active", "updated_at"])

        return APIResponse.success(message="Employee updated.", data=EmployeeDetailSerializer(emp).data)

    def delete(self, request, pk):
        emp = self._get_employee(request, pk)
        if not emp:
            return APIResponse.error(message="Employee not found.", status_code=404)
        emp.user.is_active = False
        emp.user.save(update_fields=["is_active", "updated_at"])
        return APIResponse.success(message="Employee deactivated.")


# --- Admin — Auth ---------------------------------------------------------------------------------------

class AdminLoginView(APIView):
    """POST /api/v1/admin/auth/login/ Body: { phone, password }"""
    permission_classes = [AllowAny]

    def post(self, request):
        s = AdminLoginSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            user, tokens = AdminAuthService.login(s.validated_data["phone"], s.validated_data["password"])
        except InvalidCredentials as e:
            return _handle(e)
        return APIResponse.success(
            message="Logged in successfully.",
            data={
                "user": {"id": str(user.id), "full_name": user.full_name, "phone": user.phone},
                "tokens": tokens,
            },
        )


class AdminForgotPasswordView(APIView):
    """POST /api/v1/admin/auth/forgot-password/  Body: { phone }"""
    permission_classes = [AllowAny]

    def post(self, request):
        s = AdminForgotPasswordSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            OTPService.send(s.validated_data["phone"], OTPVerification.Purpose.PASSWORD_RESET)
        except (OTPRateLimited, AuthError) as e:
            return _handle(e)
        return APIResponse.success(
            message="OTP sent to your registered phone.",
            data={"phone": s.validated_data["phone"]},
        )


class AdminVerifyOTPView(APIView):
    """POST /api/v1/admin/auth/otp/verify/  Body: { phone, otp_code }"""
    permission_classes = [AllowAny]

    def post(self, request):
        phone = request.data.get("phone", "").replace(" ", "")
        otp_code = request.data.get("otp_code", "")
        if not phone or not otp_code:
            return APIResponse.error(
                errors={"detail": ["phone and otp_code are required."]},
                message="Invalid input.",
            )
        try:
            otp = OTPService.verify(phone, otp_code, OTPVerification.Purpose.PASSWORD_RESET)
        except (OTPExpired, OTPInvalid, OTPMaxAttempts, AuthError) as e:
            return _handle(e)
        return APIResponse.success(
            message="OTP verified.",
            data={"phone_verification_token": otp.verification_token},
        )


class AdminResetPasswordView(APIView):
    """POST /api/v1/admin/auth/reset-password/  Body: { phone, phone_verification_token, new_password }"""
    permission_classes = [AllowAny]

    def post(self, request):
        s = AdminResetPasswordSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data
        try:
            AdminAuthService.reset_password(d["phone"], d["phone_verification_token"], d["new_password"])
        except (InvalidToken, InvalidCredentials, AuthError) as e:
            return _handle(e)
        return APIResponse.success(message="Password reset successfully. Please log in.")


class AdminProfileView(APIView):
    """
    GET /api/v1/admin/profile/
    PATCH /api/v1/admin/profile/
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        return APIResponse.success(data=AdminProfileSerializer(request.user).data)

    def patch(self, request):
        s = AdminProfileSerializer(request.user, data=request.data, partial=True)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        s.save()
        return APIResponse.success(message="Profile updated.", data=s.data)


# --- Admin — Restaurant & Branch Approvals --------------------------------------------------

class AdminRestaurantApproveView(APIView):
    """POST /api/v1/admin/restaurants/{id}/approve/"""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            AdminAuthService.approve_restaurant(pk)
        except (NotFound, AuthError) as e:
            return _handle(e)
        return APIResponse.success(message="Restaurant approved and owner account activated.")


class AdminRestaurantRejectView(APIView):
    """POST /api/v1/admin/restaurants/{id}/reject/  Body: { reason } (optional)"""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            AdminAuthService.reject_restaurant(pk, reason=request.data.get("reason", ""))
        except (NotFound, AuthError) as e:
            return _handle(e)
        return APIResponse.success(message="Restaurant rejected.")


class AdminBranchApproveView(APIView):
    """POST /api/v1/admin/branches/{id}/approve/"""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            AdminAuthService.approve_branch(pk)
        except (NotFound, AuthError) as e:
            return _handle(e)
        return APIResponse.success(message="Branch approved and activated.")


class AdminBranchRejectView(APIView):
    """POST /api/v1/admin/branches/{id}/reject/"""
    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        try:
            AdminAuthService.reject_branch(pk)
        except (NotFound, AuthError) as e:
            return _handle(e)
        return APIResponse.success(message="Branch rejected/deactivated.")



# --- Shared ----------------------------------------------------------------------------

class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Body: { refresh }
    Blacklists the refresh token. Works for all roles.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token_str = request.data.get("refresh")
        if not token_str:
            return APIResponse.error(errors={"refresh": ["This field is required."]})
        try:
            RefreshToken(token_str).blacklist()
        except TokenError as e:
            return APIResponse.error(errors={"refresh": [str(e)]}, message="Invalid token.")
        return APIResponse.success(message="Logged out successfully.")



# --- Admin — Customer management -------------------------------------------------------------

class AdminCustomerListView(APIView):
    """
    GET /api/v1/admin/customers/
    Query params: search, is_active (true|false), page, page_size
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = AdminAuthService.list_customers(
            search=request.query_params.get("search", ""),
            is_active=request.query_params.get("is_active", ""),
        )
        return _paginate(request, qs, AdminCustomerListSerializer)


class AdminCustomerDetailView(APIView):
    """
    GET /api/v1/admin/customers/{id}/   — detail
    PATCH /api/v1/admin/customers/{id}/   — activate / deactivate  { is_active: bool }
    DELETE /api/v1/admin/customers/{id}/   — hard delete
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, pk):
        try:
            user = AdminAuthService.get_customer(pk)
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(data=AdminCustomerListSerializer(user).data)

    def patch(self, request, pk):
        is_active = request.data.get("is_active")
        if is_active is None:
            return APIResponse.error(errors={"is_active": ["This field is required."]})
        try:
            user = AdminAuthService.set_customer_active(pk, bool(is_active))
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(
            message=f"Customer {'activated' if user.is_active else 'deactivated'}.",
            data=AdminCustomerListSerializer(user).data,
        )

    def delete(self, request, pk):
        try:
            AdminAuthService.delete_customer(pk)
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(message="Customer deleted.")


# --- Admin — Owner management -------------------------------------------------------

class AdminOwnerListView(APIView):
    """
    GET /api/v1/admin/owners/
    Query params: search, is_active (true|false), status (pending|approved|rejected),
                  page, page_size
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        owners = AdminAuthService.list_owners(
            search=request.query_params.get("search", ""),
            is_active=request.query_params.get("is_active", ""),
            status=request.query_params.get("status", ""),
        )
        return _paginate_list(request, owners, AdminOwnerListSerializer)


class AdminOwnerDetailView(APIView):
    """
    GET /api/v1/admin/owners/{id}/ — detail (owner + their restaurant snapshot)
    PATCH /api/v1/admin/owners/{id}/ — activate / deactivate  { is_active: bool }
    DELETE /api/v1/admin/owners/{id}/ — hard delete (cascades to restaurant, branches, staff)
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, pk):
        try:
            user = AdminAuthService.get_owner(pk)
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(data=AdminOwnerListSerializer(user).data)

    def patch(self, request, pk):
        is_active = request.data.get("is_active")
        if is_active is None:
            return APIResponse.error(errors={"is_active": ["This field is required."]})
        try:
            user = AdminAuthService.set_owner_active(pk, bool(is_active))
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(
            message=f"Owner {'activated' if user.is_active else 'deactivated'}.",
        )

    def delete(self, request, pk):
        try:
            AdminAuthService.delete_owner(pk)
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(message="Owner and all associated data deleted.")


# --- Admin — Employee management (read-only + deactivate) ----------------------------

class AdminEmployeeListView(APIView):
    """
    GET /api/v1/admin/employees/
    Query params: search, is_active (true|false), restaurant_id, page, page_size
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = AdminAuthService.list_employees(
            search=request.query_params.get("search", ""),
            is_active=request.query_params.get("is_active", ""),
            restaurant_id=request.query_params.get("restaurant_id", ""),
        )
        return _paginate(request, qs, AdminEmployeeListSerializer)


class AdminEmployeeDetailView(APIView):
    """
    GET /api/v1/admin/employees/{id}/   — detail
    PATCH /api/v1/admin/employees/{id}/   — activate / deactivate  { is_active: bool }
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def _get_employee(self, pk):
        from apps.restaurants.models import Employee as Emp
        try:
            return Emp.objects.select_related("user", "branch", "branch__restaurant").get(id=pk)
        except Emp.DoesNotExist:
            return None

    def get(self, request, pk):
        emp = self._get_employee(pk)
        if not emp:
            return APIResponse.error(message="Employee not found.", status_code=404)
        return APIResponse.success(data=AdminEmployeeListSerializer(emp).data)

    def patch(self, request, pk):
        emp = self._get_employee(pk)
        if not emp:
            return APIResponse.error(message="Employee not found.", status_code=404)
        is_active = request.data.get("is_active")
        if is_active is None:
            return APIResponse.error(errors={"is_active": ["This field is required."]})
        emp.user.is_active = bool(is_active)
        emp.user.save(update_fields=["is_active", "updated_at"])
        return APIResponse.success(
            message=f"Employee {'activated' if emp.user.is_active else 'deactivated'}.",
            data=AdminEmployeeListSerializer(emp).data,
        )


# --- Admin — Restaurant management (list / detail — approve/reject already exist) --------------

class AdminRestaurantListView(APIView):
    """
    GET /api/v1/admin/restaurants/
    Query params: search, status (pending|approved|rejected), category, page, page_size
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = AdminAuthService.list_restaurants(
            search=request.query_params.get("search", ""),
            status=request.query_params.get("status", ""),
            category=request.query_params.get("category", ""),
        )
        return _paginate(request, qs, RestaurantListSerializer)


class AdminRestaurantDetailView(APIView):
    """
    GET /api/v1/admin/restaurants/{id}/
    Full restaurant detail including branches and bank info.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, pk):
        try:
            restaurant = AdminAuthService.get_restaurant(pk)
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(data=RestaurantSerializer(restaurant).data)


# --- Admin — Branch management (list / detail — approve/reject already exist) ----------

class AdminBranchListView(APIView):
    """
    GET /api/v1/admin/branches/
    Query params: search, is_active (true|false), restaurant_id, page, page_size
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        qs = AdminAuthService.list_branches(
            search=request.query_params.get("search", ""),
            is_active=request.query_params.get("is_active", ""),
            restaurant_id=request.query_params.get("restaurant_id", ""),
        )
        return _paginate(request, qs, BranchListSerializer)


class AdminBranchDetailView(APIView):
    """
    GET /api/v1/admin/branches/{id}/
    Full branch detail including opening hours.
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, pk):
        try:
            branch = AdminAuthService.get_branch(pk)
        except NotFound as e:
            return _handle(e)
        return APIResponse.success(data=BranchDetailSerializer(branch).data)
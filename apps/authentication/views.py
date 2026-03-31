import json

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from apps.utils.custom_response import APIResponse
from apps.restaurants.models import Branch, Employee
from .models import OTPVerification
from .permissions import IsCustomer, IsOwner, IsAdmin
from .serializers import (
    # Customer
    CustomerOTPSendSerializer, CustomerOTPVerifySerializer,
    CustomerProfileSerializer,
    ChangePhoneRequestSerializer, ChangePhoneVerifySerializer,
    # Employee
    EmployeeLoginSerializer,
    # Owner
    OwnerLoginSerializer, BranchSerializer,
    BranchCreateSerializer, OwnerRegSubmitSerializer,
    CreateEmployeeSerializer, EmployeeDetailSerializer,
    # Admin
    AdminLoginSerializer, AdminForgotPasswordSerializer,
    AdminResetPasswordSerializer, AdminProfileSerializer,
)
from .services import (
    OTPService, CustomerAuthService, EmployeeAuthService,
    OwnerAuthService, AdminAuthService,
    AuthError, OTPRateLimited, OTPExpired, OTPInvalid,
    OTPMaxAttempts, InvalidCredentials, InvalidToken,
)


# --- Helpers ---------------------------------------------------------------------------

def _handle(exc):
    """Map a service exception to an APIResponse error."""
    return APIResponse.error(
        errors={"detail": [str(exc)]},
        message=str(exc),
        status_code=getattr(exc, "status_code", 400),
    )


def _parse_branches(request) -> tuple[list | None, APIResponse | None]:
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


# ---Customer--------------------------------------------------------

class CustomerOTPSendView(APIView):
    """
    POST /api/v1/customer/auth/otp/send/
    Send OTP for login or phone change.
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
    Verify OTP → log in. Auto-creates profile on first login.
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
    GET   /api/v1/customer/profile/  — view profile
    PATCH /api/v1/customer/profile/  — edit name, username, email, avatar
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
    Send OTP to the NEW phone number.
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
    Verify OTP on new phone then save.
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
        except (OTPExpired, OTPInvalid, OTPMaxAttempts, AuthError) as e:
            return _handle(e)

        try:
            user = CustomerAuthService.change_phone(request.user, d["new_phone"], otp.verification_token)
        except (InvalidToken, AuthError) as e:
            return _handle(e)

        return APIResponse.success(
            message="Phone number updated successfully.",
            data={"phone": user.phone},
        )


# --- Employee -------------------------------------------------------------

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
                    "id":        str(user.id),
                    "username":  user.username,
                    "full_name": user.full_name,
                },
                "branch": {
                    "id":              str(emp.branch.id),
                    "name":            emp.branch.name,
                    "restaurant_name": emp.branch.restaurant.brand_name,
                },
                "permissions": emp.permissions,
                "tokens":      tokens,
            },
        )


# --- OWNER — Registration --------------------------------------------------

class OwnerRegOTPSendView(APIView):
    """
    POST /api/v1/owner/auth/otp/send/
    Send OTP for owner registration.
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
        return APIResponse.success(
            message="OTP sent. Valid for 5 minutes.",
            data={"phone": phone},
        )


class OwnerRegOTPVerifyView(APIView):
    """
    POST /api/v1/owner/auth/otp/verify/
    Verify registration OTP. Returns verification_token used in submit.
    Body: { phone, otp_code }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone    = request.data.get("phone", "").replace(" ", "")
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

    All registration steps in one request.
    Branches are sent as a JSON string in the 'branches' field.

    Example branches value (as a string):
    [
      {
        "name": "Riyadh Main Branch",
        "city": "Riyadh",
        "full_address": "King Fahd Road, Al Olaya",
        "min_order": "25.00",
        "opening_hours": [
          { "day": "monday",  "is_open": true,  "shifts": [{"open": "09:00", "close": "22:00"}] },
          { "day": "friday",  "is_open": true,  "shifts": [{"open": "13:00", "close": "23:00"}] },
          { "day": "sunday",  "is_open": false, "shifts": [] }
        ]
      }
    ]
    """
    permission_classes = [AllowAny]

    def post(self, request):
        # Step 1: Validate all flat fields
        s = OwnerRegSubmitSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")

        # Step 2: Parse and validate branches
        branches, err = _parse_branches(request)
        if err:
            return err

        # Step 3: Run the full registration in one transaction
        try:
            OwnerAuthService.register(s.validated_data, branches)
        except (InvalidToken, AuthError) as e:
            return _handle(e)

        return APIResponse.success(
            message="Registration submitted successfully. Pending admin approval.",
            status_code=201,
        )


# --- OWNER — Login & Dashboard -------------------------------------------------------------

class OwnerLoginView(APIView):
    """
    POST /api/v1/owner/auth/login/
    Body: { phone, password }
    Returns tokens + branch list for the branch selector screen.
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

        branches = OwnerAuthService.get_branches(user)
        return APIResponse.success(
            message="Logged in. Select a branch to continue.",
            data={
                "user":     {"id": str(user.id), "full_name": user.full_name},
                "branches": BranchSerializer(branches, many=True).data,
                "tokens":   tokens,
            },
        )


class OwnerBranchListView(APIView):
    """
    GET /api/v1/owner/branches/
    Re-fetch branch list (for branch switching after login).
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        branches = OwnerAuthService.get_branches(request.user)
        return APIResponse.success(
            data=BranchSerializer(branches, many=True).data,
            meta={"count": branches.count()},
        )


# --- OWNER — Staff management -------------------------------------------

class OwnerStaffListCreateView(APIView):
    """
    GET  /api/v1/owner/staff/  — list all employees across all branches
    POST /api/v1/owner/staff/  — create new employee account
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
            emp = Employee.objects.create(
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
    GET    /api/v1/owner/staff/{id}/  — employee detail
    PATCH  /api/v1/owner/staff/{id}/  — update permissions / branch / active status
    DELETE /api/v1/owner/staff/{id}/  — deactivate employee
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
        branch_id   = request.data.get("branch_id")
        is_active   = request.data.get("is_active")

        if permissions is not None:
            invalid = set(permissions) - set(Employee.ALL_PERMISSIONS)
            if invalid:
                return APIResponse.error(
                    errors={"permissions": [f"Invalid permissions: {sorted(invalid)}"]},
                )
            emp.permissions = list(permissions)
            emp.save(update_fields=["permissions", "updated_at"])

        if branch_id is not None:
            try:
                branch = Branch.objects.get(
                    id=branch_id, restaurant__owner=request.user, is_active=True
                )
                emp.branch = branch
                emp.save(update_fields=["branch", "updated_at"])
            except Branch.DoesNotExist:
                return APIResponse.error(errors={"branch_id": ["Branch not found."]})

        if is_active is not None:
            emp.user.is_active = bool(is_active)
            emp.user.save(update_fields=["is_active", "updated_at"])

        return APIResponse.success(
            message="Employee updated.",
            data=EmployeeDetailSerializer(emp).data,
        )

    def delete(self, request, pk):
        emp = self._get_employee(request, pk)
        if not emp:
            return APIResponse.error(message="Employee not found.", status_code=404)
        emp.user.is_active = False
        emp.user.save(update_fields=["is_active", "updated_at"])
        return APIResponse.success(message="Employee deactivated.")


# --- ADMIN --------------------------------------------------------------------------

class AdminLoginView(APIView):
    """
    POST /api/v1/admin/auth/login/
    Body: { phone, password }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        s = AdminLoginSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            user, tokens = AdminAuthService.login(
                s.validated_data["phone"], s.validated_data["password"]
            )
        except InvalidCredentials as e:
            return _handle(e)
        return APIResponse.success(
            message="Logged in successfully.",
            data={
                "user":   {"id": str(user.id), "full_name": user.full_name, "phone": user.phone},
                "tokens": tokens,
            },
        )


class AdminForgotPasswordView(APIView):
    """
    POST /api/v1/admin/auth/forgot-password/
    Body: { phone }
    """
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
    """
    POST /api/v1/admin/auth/otp/verify/
    Body: { phone, otp_code }
    Returns phone_verification_token for use in reset-password.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone    = request.data.get("phone", "").replace(" ", "")
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
    """
    POST /api/v1/admin/auth/reset-password/
    Body: { phone, phone_verification_token, new_password }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        s = AdminResetPasswordSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        d = s.validated_data
        try:
            AdminAuthService.reset_password(
                d["phone"], d["phone_verification_token"], d["new_password"]
            )
        except (InvalidToken, InvalidCredentials, AuthError) as e:
            return _handle(e)
        return APIResponse.success(message="Password reset successfully. Please log in.")


class AdminProfileView(APIView):
    """
    GET   /api/v1/admin/profile/  — view profile
    PATCH /api/v1/admin/profile/  — edit full_name, username, email, phone, avatar
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


# --- SHARED ----------------------------------------------------------------------

class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Blacklists the refresh token. Works for all roles.
    Body: { refresh }
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

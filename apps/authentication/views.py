"""
Views follow one pattern:
  1. Validate input via serializer
  2. Call service method
  3. Map service exceptions → APIResponse.error()
  4. Return APIResponse.success()
Zero business logic in views.
"""
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import JSONParser
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from rest_framework.parsers import MultiPartParser, FormParser

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
    OwnerRegSubmitSerializer,
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


# ── Error helper ──────────────────────────────────────────────────────────────

def _handle(exc) -> APIResponse:
    """Map service exceptions → APIResponse.error with correct HTTP status."""
    return APIResponse.error(
        errors={"detail": [str(exc)]},
        message=str(exc),
        status_code=getattr(exc, "status_code", 400),
    )


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOMER
# ─────────────────────────────────────────────────────────────────────────────

class CustomerOTPSendView(APIView):
    """
    POST /api/v1/customer/auth/otp/send/

    Send a 6-digit OTP for login or phone-change verification.

    Request body:
        phone   (str, required) — Saudi phone, e.g. +966512345678
        purpose (str)           — "login" | "change_phone"  (default: "login")

    Responses:
        200 — OTP sent successfully
        400 — Validation error
        429 — Rate limited (too many requests)
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

    Request body:
        phone    (str) — Saudi phone
        otp_code (str) — 6-digit code

    Response data:
        user   — { id, full_name, phone, is_new_user }
        tokens — { access, refresh }

    Responses:
        200 — Logged in (or profile created)
        400 — Invalid OTP / validation error
        401 — Account deactivated
        429 — Too many attempts
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

    View or edit profile.
    Editable fields: full_name, username, email, avatar
    Note: phone is NOT editable here — use the change-phone flow.

    Auth: Bearer token (customer role)
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

    Step 1 of phone change — send OTP to the NEW phone number.

    Request body:
        phone (str) — the NEW phone number

    Auth: Bearer token (customer role)
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

    Step 2 of phone change — verify OTP then save the new number.

    Flow:
        1. Client calls /change-phone/request/ → OTP sent to new number
        2. User enters OTP → client calls this endpoint
        3. OTP verified → phone updated

    Request body:
        new_phone                (str) — the new phone number
        otp_code                 (str) — 6-digit code received on new phone
        phone_verification_token (str) — token returned from OTP verify step

    Auth: Bearer token (customer role)
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


# ─────────────────────────────────────────────────────────────────────────────
# EMPLOYEE
# ─────────────────────────────────────────────────────────────────────────────

class EmployeeLoginView(APIView):
    """
    POST /api/v1/employee/auth/login/

    Login with username and password (credentials set by restaurant owner).

    Request body:
        username (str)
        password (str)

    Response data:
        user        — { id, username, full_name }
        branch      — { id, name, restaurant_name }
        permissions — list of granted permissions
        tokens      — { access, refresh }

    Responses:
        200 — Logged in
        401 — Invalid credentials / deactivated
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
                    "restaurant_name": emp.branch.restaurant.name,
                },
                "permissions": emp.permissions,
                "tokens":      tokens,
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# OWNER — Registration
# ─────────────────────────────────────────────────────────────────────────────

class OwnerRegOTPSendView(APIView):
    """
    POST /api/v1/owner/auth/register/otp/send/

    Step 1a — Send OTP to the owner's phone during registration.
    This is separate from login OTP so the purpose is "owner_register".

    Request body:
        phone (str) — Saudi phone number

    Responses:
        200 — OTP sent
        429 — Rate limited
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
    POST /api/v1/owner/auth/register/otp/verify/

    Step 1b — Verify OTP and receive a phone_verification_token.
    This token is required when submitting the full registration.

    Request body:
        phone    (str) — Saudi phone number
        otp_code (str) — 6-digit code

    Response data:
        phone_verification_token (str) — short-lived token, valid until used

    Responses:
        200 — Verified, token returned
        400 — Invalid/expired OTP
        429 — Too many attempts
    """
    permission_classes = [AllowAny]

    def post(self, request):
        phone    = request.data.get("phone", "").replace(" ", "")
        otp_code = request.data.get("otp_code", "")
        if not phone or not otp_code:
            return APIResponse.error(errors={"detail": ["phone and otp_code are required."]})
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

    Final registration step — submit all 6 steps at once.

    The frontend collects data across steps 1-6 and posts everything here.
    The account is created in PENDING status and awaits admin approval.

    Request body (multipart/form-data for file uploads):
        # Step 1
        full_name                (str)
        phone                    (str)
        email                    (str)
        phone_verification_token (str)   — from /register/otp/verify/
        password                 (str, min 8 chars)

        # Step 2
        legal_name        (str)
        brand_name        (str)
        category          (str)   — fast_food | casual | fine_dining | cafe | bakery | pizza | sushi | shawarma | seafood | other
        logo              (file, optional)
        short_description (str, optional)

        # Step 3
        cr_number                 (str)
        vat_number                (str)
        cr_document               (file)
        vat_certificate           (file)
        short_address             (str)
        street_name               (str)
        building_number           (str)
        building_secondary_number (str, optional)
        district                  (str)
        postal_code               (str)
        unit_number               (str, optional)
        city                      (str)
        country                   (str, default: "Saudi Arabia")

        # Step 4-5: Branches (JSON array in "branches" field)
        branches[0][name]                   (str)
        branches[0][city]                   (str)
        branches[0][full_address]           (str)
        branches[0][min_order]              (decimal)
        branches[0][opening_hours][0][day]       (str)
        branches[0][opening_hours][0][is_open]   (bool)
        branches[0][opening_hours][0][shifts][0][open]  (str, e.g. "09:00")
        branches[0][opening_hours][0][shifts][0][close] (str, e.g. "22:00")
        ... (repeat for more branches / more days)

        # Step 6
        bank_name           (str)   — al_rajhi | snb | riyad | samba | alinma | bsf | arab | sib | other
        account_holder_name (str)
        iban                (str)   — SA + 22 digits
        bank_iban_pdf       (file)

    Response data:
        message — "Registration submitted. Pending admin approval."

    Responses:
        201 — Created, pending approval
        400 — Validation error
        400 — Phone already registered as owner
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser] 

    def post(self, request):
        s = OwnerRegSubmitSerializer(data=request.data)
        if not s.is_valid():
            return APIResponse.error(errors=s.errors, message="Invalid input.")
        try:
            OwnerAuthService.register(s.validated_data)
        except (InvalidToken, AuthError) as e:
            return _handle(e)
        return APIResponse.success(
            message="Registration submitted. Pending admin approval.",
            status_code=201,
        )


# ─────────────────────────────────────────────────────────────────────────────
# OWNER — Login & Branch selection
# ─────────────────────────────────────────────────────────────────────────────

class OwnerLoginView(APIView):
    """
    POST /api/v1/owner/auth/login/

    Login with phone and password.
    Returns tokens + branch list so the client can show the branch selector.

    Request body:
        phone    (str)
        password (str)

    Response data:
        user     — { id, full_name }
        branches — list of active branches
        tokens   — { access, refresh }

    Responses:
        200 — Logged in
        401 — Invalid credentials / deactivated / pending approval
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

    List the owner's active branches.
    Used on the branch-selector screen and when switching branches.

    Auth: Bearer token (owner role)
    """
    permission_classes = [IsAuthenticated, IsOwner]

    def get(self, request):
        branches = OwnerAuthService.get_branches(request.user)
        return APIResponse.success(
            data=BranchSerializer(branches, many=True).data,
            meta={"count": branches.count()},
        )


# ─────────────────────────────────────────────────────────────────────────────
# OWNER — Staff management
# ─────────────────────────────────────────────────────────────────────────────

class OwnerStaffListCreateView(APIView):
    """
    GET  /api/v1/owner/staff/   — list all staff across all branches
    POST /api/v1/owner/staff/   — create a new employee account

    POST body:
        username    (str)
        phone       (str, optional)
        password    (str, min 6 chars)
        branch_id   (UUID)
        permissions (list) — subset of: dashboard | edit_menu | confirm_order | view_reports | manage_staff

    Auth: Bearer token (owner role)
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
        d = s.validated_data

        from django.db import transaction
        with transaction.atomic():
            user = request.user.__class__.objects.create_user(
                phone=d.get("phone") or None,
                password=d["password"],
                username=d["username"],
                role="employee",
            )
            branch = Branch.objects.get(id=d["branch_id"])
            emp = Employee.objects.create(
                user=user,
                branch=branch,
                permissions=list(d["permissions"]),
                created_by=request.user,
            )

        return APIResponse.success(
            message="Employee account created.",
            data=EmployeeDetailSerializer(emp).data,
            status_code=201,
        )


class OwnerStaffDetailView(APIView):
    """
    GET    /api/v1/owner/staff/<pk>/   — employee detail
    PATCH  /api/v1/owner/staff/<pk>/   — update permissions / branch / active status
    DELETE /api/v1/owner/staff/<pk>/   — deactivate employee

    PATCH body (all optional):
        permissions (list)  — replace the full permissions list
        branch_id   (UUID)  — move employee to another branch
        is_active   (bool)  — activate / deactivate

    Auth: Bearer token (owner role)
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
                    errors={"permissions": [f"Invalid permissions: {invalid}"]},
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


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────────────────────────────────────

class AdminLoginView(APIView):
    """
    POST /api/v1/admin/auth/login/

    Request body:
        phone    (str)
        password (str)

    Response data:
        user   — { id, full_name, phone }
        tokens — { access, refresh }
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

    Step 1 — send password-reset OTP to admin's registered phone.

    Request body:
        phone (str)
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

    Step 2 — verify OTP, receive phone_verification_token for password reset.

    Request body:
        phone    (str)
        otp_code (str) — 6-digit code

    Response data:
        phone_verification_token (str)
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

    Step 3 — set new password using the verification token.

    Request body:
        phone                    (str)
        phone_verification_token (str) — from /otp/verify/
        new_password             (str, min 8 chars)
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
    GET   /api/v1/admin/profile/
    PATCH /api/v1/admin/profile/

    View or edit admin profile.
    Editable fields: full_name, username, email, phone, avatar

    Auth: Bearer token (admin role)
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


# ─────────────────────────────────────────────────────────────────────────────
# SHARED
# ─────────────────────────────────────────────────────────────────────────────

class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/

    Blacklist the refresh token. Works for all roles.

    Request body:
        refresh (str) — refresh token to invalidate

    Auth: Bearer token (any authenticated role)
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
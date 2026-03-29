"""
All auth business logic lives here. Views only call services.
No HTTP objects (Request/Response) in this file.
"""
import random
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from .models import OTPVerification, User

log = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────

class AuthError(Exception):
    status_code = 400

class OTPRateLimited(AuthError):
    status_code = 429

class OTPExpired(AuthError):
    pass

class OTPInvalid(AuthError):
    pass

class OTPMaxAttempts(AuthError):
    status_code = 429

class InvalidCredentials(AuthError):
    status_code = 401

class InvalidToken(AuthError):
    pass


# ── OTP Service ───────────────────────────────────────────────────────────────

class OTPService:

    @classmethod
    def send(cls, phone: str, purpose: str) -> OTPVerification:
        cls._check_rate_limit(phone, purpose)

        # Invalidate previous pending OTPs
        OTPVerification.objects.filter(phone=phone, purpose=purpose, is_used=False).update(is_used=True)

        code = str(random.randint(100_000, 999_999))
        otp  = OTPVerification.objects.create(
            phone=phone,
            otp_code=code,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(seconds=OTPVerification.TTL_SECONDS),
        )
        cls._send_sms(phone, code)
        log.info("OTP sent phone=%s purpose=%s", phone, purpose)
        return otp

    @classmethod
    def verify(cls, phone: str, code: str, purpose: str) -> OTPVerification:
        try:
            otp = OTPVerification.objects.filter(
                phone=phone, purpose=purpose, is_used=False
            ).latest("created_at")
        except OTPVerification.DoesNotExist:
            raise OTPInvalid("No active OTP found for this number.")

        if otp.is_expired:
            raise OTPExpired("OTP has expired. Request a new one.")

        if otp.attempts >= OTPVerification.MAX_ATTEMPTS:
            raise OTPMaxAttempts("Too many attempts. Request a new OTP.")

        if not otp.verify(code):
            remaining = OTPVerification.MAX_ATTEMPTS - otp.attempts
            raise OTPInvalid(f"Invalid OTP. {remaining} attempt(s) remaining.")

        return otp

    @staticmethod
    def get_verified_otp(phone: str, token: str, purpose: str) -> OTPVerification:
        try:
            return OTPVerification.objects.get(
                phone=phone, purpose=purpose,
                verification_token=token, is_verified=True,
            )
        except OTPVerification.DoesNotExist:
            raise InvalidToken("Verification token is invalid or already used.")

    # ── Private ───────────────────────────────────────────────────────────────

    @classmethod
    def _check_rate_limit(cls, phone: str, purpose: str):
        one_hour_ago = timezone.now() - timedelta(hours=1)
        count = OTPVerification.objects.filter(
            phone=phone, purpose=purpose, created_at__gte=one_hour_ago
        ).count()
        if count >= OTPVerification.MAX_SENDS_HOUR:
            raise OTPRateLimited("Too many OTP requests. Try again later.")

        last = OTPVerification.objects.filter(
            phone=phone, purpose=purpose
        ).order_by("-created_at").first()
        if last:
            elapsed = (timezone.now() - last.created_at).total_seconds()
            if elapsed < OTPVerification.RESEND_COOLDOWN:
                wait = int(OTPVerification.RESEND_COOLDOWN - elapsed)
                raise OTPRateLimited(f"Wait {wait}s before requesting another OTP.")

    @staticmethod
    def _send_sms(phone: str, code: str):
        # TODO: integrate Unifonic / Twilio / any Saudi SMS provider
        log.debug("SMS → %s | code: %s", phone, code)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def make_tokens(user: User, extra_claims: dict = None) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    for k, v in (extra_claims or {}).items():
        refresh[k] = v
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


# ── Customer auth ─────────────────────────────────────────────────────────────

class CustomerAuthService:

    @staticmethod
    @transaction.atomic
    def login_or_create(phone: str, otp_code: str) -> tuple[User, dict, bool]:
        """
        Verify OTP, then get-or-create the customer user.
        Returns (user, tokens, is_new_user).
        """
        OTPService.verify(phone, otp_code, OTPVerification.Purpose.LOGIN)

        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={
                "role":              User.Role.CUSTOMER,
                "is_phone_verified": True,
                "is_active":         True,
            },
        )
        if not user.is_active:
            raise InvalidCredentials("Your account has been deactivated.")

        tokens = make_tokens(user)
        return user, tokens, created

    @staticmethod
    @transaction.atomic
    def change_phone(user: User, new_phone: str, otp_token: str) -> User:
        """Verify OTP token for new_phone, then update user's phone."""
        OTPService.get_verified_otp(new_phone, otp_token, OTPVerification.Purpose.CHANGE_PHONE)

        if User.objects.filter(phone=new_phone).exclude(id=user.id).exists():
            raise AuthError("This phone number is already in use.")

        user.phone = new_phone
        user.is_phone_verified = True
        user.save(update_fields=["phone", "is_phone_verified", "updated_at"])
        return user


# ── Employee auth ─────────────────────────────────────────────────────────────

class EmployeeAuthService:

    @staticmethod
    def login(username: str, password: str) -> tuple[User, dict]:
        try:
            user = (
                User.objects
                .select_related("employee_profile__branch__restaurant")
                .get(username=username, role=User.Role.EMPLOYEE)
            )
        except User.DoesNotExist:
            raise InvalidCredentials("Invalid username or password.")

        if not user.check_password(password):
            raise InvalidCredentials("Invalid username or password.")

        if not user.is_active:
            raise InvalidCredentials("Your account has been deactivated.")

        emp = user.employee_profile
        tokens = make_tokens(user, extra_claims={
            "branch_id":     str(emp.branch_id),
            "branch_name":   emp.branch.name,
            "restaurant_id": str(emp.branch.restaurant_id),
            "permissions":   emp.permissions,
        })
        return user, tokens


# ── Owner auth ────────────────────────────────────────────────────────────────

class OwnerAuthService:

    @staticmethod
    def login(phone: str, password: str) -> tuple[User, dict]:
        try:
            user = User.objects.get(phone=phone, role=User.Role.OWNER)
        except User.DoesNotExist:
            raise InvalidCredentials("Invalid phone number or password.")

        if not user.check_password(password):
            raise InvalidCredentials("Invalid phone number or password.")

        if not user.is_active:
            raise InvalidCredentials("Your account has been deactivated.")

        tokens = make_tokens(user)
        return user, tokens

    @staticmethod
    def get_branches(user: User):
        from apps.restaurants.models import Branch
        return (
            Branch.objects
            .filter(restaurant__owner=user, is_active=True)
            .select_related("restaurant")
            .order_by("restaurant__name", "name")
        )


# ── Admin auth ────────────────────────────────────────────────────────────────

class AdminAuthService:

    @staticmethod
    def login(phone: str, password: str) -> tuple[User, dict]:
        try:
            user = User.objects.get(phone=phone, role=User.Role.ADMIN)
        except User.DoesNotExist:
            raise InvalidCredentials("Invalid phone number or password.")

        if not user.check_password(password):
            raise InvalidCredentials("Invalid phone number or password.")

        if not user.is_active:
            raise InvalidCredentials("Your account has been deactivated.")

        return user, make_tokens(user)

    @staticmethod
    @transaction.atomic
    def reset_password(phone: str, otp_token: str, new_password: str) -> User:
        OTPService.get_verified_otp(phone, otp_token, OTPVerification.Purpose.PASSWORD_RESET)
        try:
            user = User.objects.get(phone=phone, role=User.Role.ADMIN)
        except User.DoesNotExist:
            raise InvalidCredentials("No admin account found for this number.")
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        return user

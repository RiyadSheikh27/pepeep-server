"""
All auth business logic lives here.
Views only call services — no HTTP objects (Request/Response) in this file.
"""
import random
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from .models import OTPVerification, User

log = logging.getLogger(__name__)


# --- Exceptions -----------------------------------------------------------

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


# --- OTP Service ----------------------------------------------------------

class OTPService:

    @classmethod
    def send(cls, phone: str, purpose: str) -> OTPVerification:
        cls._check_rate_limit(phone, purpose)

        # Invalidate any previous active OTPs for this phone + purpose
        OTPVerification.objects.filter(
            phone=phone, purpose=purpose, is_used=False
        ).update(is_used=True)

        code = str(random.randint(100_000, 999_999))
        otp  = OTPVerification.objects.create(
            phone=phone,
            otp_code=code,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(seconds=OTPVerification.TTL_SECONDS),
        )

        cls._send_sms(phone, code)
        log.info("OTP sent phone=%s purpose=%s", phone, purpose)
        print(code)
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
                phone=phone,
                purpose=purpose,
                verification_token=token,
                is_verified=True,
            )
        except OTPVerification.DoesNotExist:
            raise InvalidToken("Verification token is invalid or already used.")

    # --- Private ---------------------------------------------------------------------

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


# --- JWT helpers --------------------------------------------------------------

def make_tokens(user: User, extra_claims: dict = None) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    for k, v in (extra_claims or {}).items():
        refresh[k] = v
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


# --- Customer -----------------------------------------------------------------

class CustomerAuthService:

    @staticmethod
    @transaction.atomic
    def login_or_create(phone: str, otp_code: str) -> tuple[User, dict, bool]:
        """Verify OTP → get-or-create customer. Returns (user, tokens, is_new)."""
        OTPService.verify(phone, otp_code, OTPVerification.Purpose.LOGIN)

        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={
                "role": User.Role.CUSTOMER,
                "is_phone_verified": True,
                "is_active": True,
            },
        )
        if not user.is_active:
            raise InvalidCredentials("Your account has been deactivated.")

        return user, make_tokens(user), created

    @staticmethod
    @transaction.atomic
    def change_phone(user: User, new_phone: str, otp_token: str) -> User:
        """Verify token for new_phone, then update user's phone."""
        OTPService.get_verified_otp(new_phone, otp_token, OTPVerification.Purpose.CHANGE_PHONE)

        if User.objects.filter(phone=new_phone).exclude(id=user.id).exists():
            raise AuthError("This phone number is already in use.")

        user.phone             = new_phone
        user.is_phone_verified = True
        user.save(update_fields=["phone", "is_phone_verified", "updated_at"])
        return user


# --- Employee ---------------------------------------------------------------------

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

        emp    = user.employee_profile
        tokens = make_tokens(user, extra_claims={
            "branch_id":     str(emp.branch_id),
            "branch_name":   emp.branch.name,
            "restaurant_id": str(emp.branch.restaurant_id),
            "permissions":   emp.permissions,
        })
        return user, tokens


# --- Owner --------------------------------------------------------------

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

        return user, make_tokens(user)

    @staticmethod
    def get_branches(user: User):
        from apps.restaurants.models import Branch
        return (
            Branch.objects
            .filter(restaurant__owner=user, is_active=True)
            .select_related("restaurant")
            .order_by("restaurant__brand_name", "name")
        )

    @staticmethod
    @transaction.atomic
    def register(data: dict, branches: list) -> User:
        """
        Create owner User → Restaurant → Branches → BranchOpeningHours → BankDetail
        in a single atomic transaction.

        Args:
            data:     validated data from OwnerRegSubmitSerializer
            branches: list of validated branch dicts from BranchCreateSerializer
        """
        from apps.restaurants.models import (
            Restaurant, Branch, BranchOpeningHours, RestaurantBankDetail
        )

        phone = data["phone"]
        token = data["phone_verification_token"]

        # 1. Confirm phone ownership via OTP token
        OTPService.get_verified_otp(phone, token, OTPVerification.Purpose.OWNER_REGISTER)

        # 2. Check no existing owner account with this phone
        if User.objects.filter(phone=phone, role=User.Role.OWNER).exists():
            raise AuthError("An owner account with this phone already exists.")

        # 3. Create owner user (inactive until admin approves)
        user = User.objects.create_user(
            phone=phone,
            password=data["password"],
            email=data.get("email"),
            full_name=data.get("full_name", ""),
            role=User.Role.OWNER,
            is_active=False,
            is_phone_verified=True,
        )

        # 4. Create restaurant
        restaurant = Restaurant.objects.create(
            owner=user,
            legal_name=data["legal_name"],
            brand_name=data["brand_name"],
            category=data["category"],
            logo=data.get("logo"),
            short_description=data.get("short_description", ""),
            cr_number=data["cr_number"],
            vat_number=data["vat_number"],
            cr_document=data["cr_document"],
            vat_certificate=data["vat_certificate"],
            short_address=data.get("short_address", ""),
            street_name=data["street_name"],
            building_number=data["building_number"],
            building_secondary_number=data.get("building_secondary_number", ""),
            district=data["district"],
            postal_code=data["postal_code"],
            unit_number=data.get("unit_number", ""),
            city=data["city"],
            country=data.get("country", "Saudi Arabia"),
            status=Restaurant.Status.PENDING,
            is_active=False,
        )


        for branch_data in branches:
            branch = Branch.objects.create(
                restaurant=restaurant,
                name=branch_data["name"],
                city=branch_data["city"],
                full_address=branch_data["full_address"],
                min_order=branch_data["min_order"],
                is_active=False,
            )

            for hours_data in branch_data.get("opening_hours", []):
                # Normalise shift times to plain strings before saving to JSONField
                shifts = [
                    {
                        "open":  s["open"].strftime("%H:%M") if hasattr(s["open"], "strftime") else s["open"],
                        "close": s["close"].strftime("%H:%M") if hasattr(s["close"], "strftime") else s["close"],
                    }
                    for s in hours_data.get("shifts", [])
                ]

                BranchOpeningHours.objects.create(
                    branch=branch,
                    day=hours_data["day"],
                    is_open=hours_data.get("is_open", True),
                    shifts=shifts,
                )

        # 6. Create bank details
        RestaurantBankDetail.objects.create(
            restaurant=restaurant,
            bank_name=data["bank_name"],
            account_holder_name=data["account_holder_name"],
            iban=data["iban"],
            bank_iban_pdf=data["bank_iban_pdf"],
        )

        log.info("Owner registration submitted: user=%s phone=%s", user.id, phone)
        return user


# --- Admin ------------------------------------------------------------------

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

"""
All auth business logic lives here.
Views only call services — no HTTP objects (Request/Response) in this file.
"""
import random
import logging
from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from .models import OTPVerification, User

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

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

class NotFound(AuthError):
    status_code = 404


# ---------------------------------------------------------------------------
# OTP Service
# ---------------------------------------------------------------------------

class OTPService:

    @classmethod
    def send(cls, phone: str, purpose: str) -> OTPVerification:
        cls._check_rate_limit(phone, purpose)

        # Invalidate previous active OTPs for this phone + purpose
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
        print(code)   # TODO: remove in production
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

    # --- Private -----------------------------------------------------------

    @classmethod
    def _check_rate_limit(cls, phone: str, purpose: str):
        one_hour_ago = timezone.now() - timedelta(hours=1)
        count = OTPVerification.objects.filter(
            phone=phone, purpose=purpose, created_at__gte=one_hour_ago
        ).count()
        if count >= OTPVerification.MAX_SENDS_HOUR:
            raise OTPRateLimited("Too many OTP requests. Try again later.")

        last = OTPVerification.objects.filter(phone=phone, purpose=purpose).order_by("-created_at").first()
        if last:
            elapsed = (timezone.now() - last.created_at).total_seconds()
            if elapsed < OTPVerification.RESEND_COOLDOWN:
                wait = int(OTPVerification.RESEND_COOLDOWN - elapsed)
                raise OTPRateLimited(f"Wait {wait}s before requesting another OTP.")

    @staticmethod
    def _send_sms(phone: str, code: str):
        # TODO: integrate Unifonic / Twilio / any Saudi SMS provider
        log.debug("SMS → %s | code: %s", phone, code)


# ---------------------------------------------------------------------------
# JWT helper
# ---------------------------------------------------------------------------

def make_tokens(user: User, extra_claims: dict = None) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    for k, v in (extra_claims or {}).items():
        refresh[k] = v
    return {"refresh": str(refresh), "access": str(refresh.access_token)}


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class CustomerAuthService:

    @staticmethod
    @transaction.atomic
    def login_or_create(phone: str, otp_code: str) -> tuple[User, dict, bool]:
        """Verify OTP → get-or-create customer. Returns (user, tokens, is_new)."""
        OTPService.verify(phone, otp_code, OTPVerification.Purpose.LOGIN)

        user, created = User.objects.get_or_create(
            phone=phone,
            defaults={"role": User.Role.CUSTOMER, "is_phone_verified": True, "is_active": True},
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


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Owner
# ---------------------------------------------------------------------------

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
    def get_active_branches(user: User):
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
        """
        from apps.restaurants.models import (
            Restaurant, Branch, BranchOpeningHours, RestaurantBankDetail
        )

        phone = data["phone"]
        OTPService.get_verified_otp(phone, data["phone_verification_token"], OTPVerification.Purpose.OWNER_REGISTER)

        if User.objects.filter(phone=phone, role=User.Role.OWNER).exists():
            raise AuthError("An owner account with this phone already exists.")

        user = User.objects.create_user(
            phone=phone,
            password=data["password"],
            email=data.get("email"),
            full_name=data.get("full_name", ""),
            role=User.Role.OWNER,
            is_active=False,
            is_phone_verified=True,
        )

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

        _create_branches(restaurant, branches)

        RestaurantBankDetail.objects.create(
            restaurant=restaurant,
            bank_name=data["bank_name"],
            account_holder_name=data["account_holder_name"],
            iban=data["iban"],
            bank_iban_pdf=data["bank_iban_pdf"],
        )

        log.info("Owner registration submitted: user=%s phone=%s", user.id, phone)
        return user

    # --- Profile / Restaurant management ------------------------------------

    @staticmethod
    def get_restaurant(user: User):
        from apps.restaurants.models import Restaurant
        try:
            return Restaurant.objects.select_related("bank_detail").get(owner=user)
        except Restaurant.DoesNotExist:
            raise NotFound("Restaurant not found.")

    @staticmethod
    @transaction.atomic
    def add_branch(user: User, branch_data: dict):
        restaurant = OwnerAuthService.get_restaurant(user)
        branches   = _create_branches(restaurant, [branch_data])
        return branches[0]

    @staticmethod
    def get_branch(user: User, branch_id):
        from apps.restaurants.models import Branch
        try:
            return (
                Branch.objects
                .prefetch_related("opening_hours")
                .get(id=branch_id, restaurant__owner=user)
            )
        except Branch.DoesNotExist:
            raise NotFound("Branch not found.")

    @staticmethod
    @transaction.atomic
    def update_branch(user: User, branch_id, data: dict):
        branch = OwnerAuthService.get_branch(user, branch_id)
        for field, value in data.items():
            setattr(branch, field, value)
        branch.save()
        return branch

    @staticmethod
    @transaction.atomic
    def set_branch_opening_hours(user: User, branch_id, hours_list: list):
        """Replace all opening hours for a branch."""
        from apps.restaurants.models import BranchOpeningHours
        branch = OwnerAuthService.get_branch(user, branch_id)
        BranchOpeningHours.objects.filter(branch=branch).delete()
        _create_opening_hours(branch, hours_list)
        return branch

    @staticmethod
    @transaction.atomic
    def delete_branch(user: User, branch_id):
        """Hard-delete a branch. Only allowed if the restaurant has more than one branch."""
        from apps.restaurants.models import Branch
        branch = OwnerAuthService.get_branch(user, branch_id)
        remaining = Branch.objects.filter(restaurant=branch.restaurant).count()
        if remaining <= 1:
            raise AuthError("Cannot delete the only branch. A restaurant must have at least one branch.")
        branch.delete()


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

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

    @staticmethod
    @transaction.atomic
    def approve_restaurant(restaurant_id) -> "Restaurant":
        from apps.restaurants.models import Restaurant
        try:
            restaurant = Restaurant.objects.select_related("owner").get(id=restaurant_id)
        except Restaurant.DoesNotExist:
            raise NotFound("Restaurant not found.")

        if restaurant.status == Restaurant.Status.APPROVED:
            raise AuthError("Restaurant is already approved.")

        restaurant.status    = Restaurant.Status.APPROVED
        restaurant.is_active = True
        restaurant.save(update_fields=["status", "is_active", "updated_at"])

        # Activate the owner account
        owner           = restaurant.owner
        owner.is_active = True
        owner.save(update_fields=["is_active", "updated_at"])

        log.info("Restaurant approved: id=%s", restaurant.id)
        return restaurant

    @staticmethod
    @transaction.atomic
    def reject_restaurant(restaurant_id, reason: str = "") -> "Restaurant":
        from apps.restaurants.models import Restaurant
        try:
            restaurant = Restaurant.objects.get(id=restaurant_id)
        except Restaurant.DoesNotExist:
            raise NotFound("Restaurant not found.")

        restaurant.status = Restaurant.Status.REJECTED
        restaurant.save(update_fields=["status", "updated_at"])
        log.info("Restaurant rejected: id=%s reason=%s", restaurant.id, reason)
        return restaurant

    @staticmethod
    @transaction.atomic
    def approve_branch(branch_id) -> "Branch":
        from apps.restaurants.models import Branch
        try:
            branch = Branch.objects.select_related("restaurant").get(id=branch_id)
        except Branch.DoesNotExist:
            raise NotFound("Branch not found.")

        branch.is_active = True
        branch.save(update_fields=["is_active", "updated_at"])
        log.info("Branch approved: id=%s", branch.id)
        return branch

    # --- User management ----------------------------------------------------

    @staticmethod
    def list_customers(search: str = "", is_active: str = ""):
        qs = User.objects.filter(role=User.Role.CUSTOMER).order_by("-created_at")
        if search:
            qs = qs.filter(
                models.Q(phone__icontains=search) |
                models.Q(full_name__icontains=search) |
                models.Q(username__icontains=search)
            )
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        return qs

    @staticmethod
    def get_customer(customer_id) -> User:
        try:
            return User.objects.get(id=customer_id, role=User.Role.CUSTOMER)
        except User.DoesNotExist:
            raise NotFound("Customer not found.")

    @staticmethod
    @transaction.atomic
    def set_customer_active(customer_id, is_active: bool) -> User:
        user = AdminAuthService.get_customer(customer_id)
        user.is_active = is_active
        user.save(update_fields=["is_active", "updated_at"])
        return user

    @staticmethod
    @transaction.atomic
    def delete_customer(customer_id):
        user = AdminAuthService.get_customer(customer_id)
        user.delete()

    @staticmethod
    def list_owners(search: str = "", is_active: str = "", status: str = "") -> list:
        """
        Returns a plain list of User objects with ._restaurant attached.
        Returns a list (not a queryset) so pagination works correctly
        after the restaurant annotation step.
        """
        from apps.restaurants.models import Restaurant
        qs = User.objects.filter(role=User.Role.OWNER).order_by("-created_at")
        if search:
            qs = qs.filter(
                models.Q(phone__icontains=search) |
                models.Q(full_name__icontains=search)
            )
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        if status in [s for s, _ in Restaurant.Status.choices]:
            qs = qs.filter(restaurants__status=status)

        # Evaluate once, then attach restaurant in a single extra query
        users = list(qs)
        restaurant_map = {
            r.owner_id: r
            for r in Restaurant.objects.filter(owner__in=users).only("owner_id", "brand_name", "status")
        }
        for user in users:
            user._restaurant = restaurant_map.get(user.id)
        return users

    @staticmethod
    def get_owner(owner_id) -> User:
        from apps.restaurants.models import Restaurant
        try:
            user = User.objects.get(id=owner_id, role=User.Role.OWNER)
        except User.DoesNotExist:
            raise NotFound("Owner not found.")
        user._restaurant = Restaurant.objects.filter(owner=user).only("owner_id", "brand_name", "status").first()
        return user

    @staticmethod
    @transaction.atomic
    def set_owner_active(owner_id, is_active: bool) -> User:
        user = AdminAuthService.get_owner(owner_id)
        user.is_active = is_active
        user.save(update_fields=["is_active", "updated_at"])
        return user

    @staticmethod
    @transaction.atomic
    def delete_owner(owner_id):
        user = AdminAuthService.get_owner(owner_id)
        user.delete()

    @staticmethod
    def list_employees(search: str = "", is_active: str = "", restaurant_id: str = ""):
        from apps.restaurants.models import Employee as Emp
        qs = (
            Emp.objects
            .select_related("user", "branch", "branch__restaurant")
            .order_by("-created_at")
        )
        if search:
            qs = qs.filter(
                models.Q(user__username__icontains=search) |
                models.Q(user__phone__icontains=search)
            )
        if is_active in ("true", "false"):
            qs = qs.filter(user__is_active=(is_active == "true"))
        if restaurant_id:
            qs = qs.filter(branch__restaurant_id=restaurant_id)
        return qs

    # --- Restaurant / Branch management ------------------------------------

    @staticmethod
    def list_restaurants(search: str = "", status: str = "", category: str = ""):
        from apps.restaurants.models import Restaurant
        qs = Restaurant.objects.select_related("owner").order_by("-created_at")
        if search:
            qs = qs.filter(
                models.Q(brand_name__icontains=search) |
                models.Q(legal_name__icontains=search) |
                models.Q(owner__phone__icontains=search)
            )
        if status:
            qs = qs.filter(status=status)
        if category:
            qs = qs.filter(category=category)
        return qs

    @staticmethod
    def get_restaurant(restaurant_id):
        from apps.restaurants.models import Restaurant
        try:
            return (
                Restaurant.objects
                .select_related("owner", "bank_detail")
                .prefetch_related("branches__opening_hours")
                .get(id=restaurant_id)
            )
        except Restaurant.DoesNotExist:
            raise NotFound("Restaurant not found.")

    @staticmethod
    def list_branches(search: str = "", is_active: str = "", restaurant_id: str = ""):
        from apps.restaurants.models import Branch
        qs = Branch.objects.select_related("restaurant").prefetch_related("opening_hours").order_by("-created_at")
        if search:
            qs = qs.filter(
                models.Q(name__icontains=search) |
                models.Q(city__icontains=search) |
                models.Q(restaurant__brand_name__icontains=search)
            )
        if is_active in ("true", "false"):
            qs = qs.filter(is_active=(is_active == "true"))
        if restaurant_id:
            qs = qs.filter(restaurant_id=restaurant_id)
        return qs

    @staticmethod
    def get_branch(branch_id):
        from apps.restaurants.models import Branch
        try:
            return (
                Branch.objects
                .select_related("restaurant")
                .prefetch_related("opening_hours")
                .get(id=branch_id)
            )
        except Branch.DoesNotExist:
            raise NotFound("Branch not found.")

    @staticmethod
    @transaction.atomic
    def reject_branch(branch_id) -> "Branch":
        from apps.restaurants.models import Branch
        try:
            branch = Branch.objects.select_related("restaurant").get(id=branch_id)
        except Branch.DoesNotExist:
            raise NotFound("Branch not found.")

        branch.is_active = False
        branch.save(update_fields=["is_active", "updated_at"])
        log.info("Branch rejected/deactivated: id=%s", branch.id)
        return branch


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalise_shifts(shifts: list) -> list:
    return [
        {
            "open":  s["open"].strftime("%H:%M") if hasattr(s["open"], "strftime") else s["open"],
            "close": s["close"].strftime("%H:%M") if hasattr(s["close"], "strftime") else s["close"],
        }
        for s in shifts
    ]


def _create_opening_hours(branch, hours_list: list):
    from apps.restaurants.models import BranchOpeningHours
    for h in hours_list:
        BranchOpeningHours.objects.create(
            branch=branch,
            day=h["day"],
            is_open=h.get("is_open", True),
            shifts=_normalise_shifts(h.get("shifts", [])),
        )


def _create_branches(restaurant, branches: list) -> list:
    from apps.restaurants.models import Branch
    created = []
    for b in branches:
        branch = Branch.objects.create(
            restaurant=restaurant,
            name=b["name"],
            city=b["city"],
            full_address=b["full_address"],
            min_order=b["min_order"],
            is_active=False,
        )
        _create_opening_hours(branch, b.get("opening_hours", []))
        created.append(branch)
    return created
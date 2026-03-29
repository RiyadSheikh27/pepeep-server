import secrets
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.utils.models import TimeStampedModel
from apps.utils.validators import validate_sa_phone
from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        EMPLOYEE = "employee", "Employee"
        OWNER    = "owner",    "Owner"
        ADMIN    = "admin",    "Admin"

    # --- Identity -------------------------------------------------------------
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True, validators=[validate_sa_phone])
    username = models.CharField(max_length=50, unique=True, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    full_name = models.CharField(max_length=150, blank=True, default="")
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", null=True, blank=True)

    # --- Role & status --------------------------------------------------------
    role              = models.CharField(max_length=20, choices=Role.choices, db_index=True)
    is_active         = models.BooleanField(default=True)
    is_staff          = models.BooleanField(default=False)   # django admin access
    is_phone_verified = models.BooleanField(default=False)

    USERNAME_FIELD  = "phone"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "users"
        indexes  = [
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["username"]),
        ]

    def __str__(self):
        return self.phone or self.username or str(self.id)


# --- OTP -----------------------------------------------------------------------------

class OTPVerification(TimeStampedModel):

    class Purpose(models.TextChoices):
        LOGIN = "login",          "Login"
        CHANGE_PHONE   = "change_phone",   "Change Phone"
        PASSWORD_RESET = "password_reset", "Password Reset"

    MAX_ATTEMPTS = 5
    TTL_SECONDS = 300   # 5 min
    RESEND_COOLDOWN = 60   # 1 min between sends
    MAX_SENDS_HOUR = 5

    phone = models.CharField(max_length=20, db_index=True)
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=Purpose.choices)
    attempts = models.PositiveSmallIntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    is_used = models.BooleanField(default=False, db_index=True)
    expires_at = models.DateTimeField()
    verification_token = models.CharField(
        max_length=64, unique=True, null=True, blank=True, db_index=True,
        help_text="Returned to client after successful verify. Used in change-phone flow.",
    )

    class Meta:
        db_table = "otp_verifications"
        indexes  = [
            models.Index(fields=["phone", "purpose", "is_used"]),
            models.Index(fields=["verification_token"]),
        ]
        ordering = ["-created_at"]

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    def verify(self, code: str) -> bool:
        self.attempts += 1
        if self.is_used or self.is_expired or self.attempts > self.MAX_ATTEMPTS:
            self.save(update_fields=["attempts"])
            return False
        if self.otp_code != code:
            self.save(update_fields=["attempts"])
            return False
        self.is_verified        = True
        self.is_used            = True
        self.verification_token = secrets.token_hex(32)
        self.save(update_fields=["attempts", "is_verified", "is_used", "verification_token"])
        return True

    def __str__(self):
        return f"OTP({self.phone}, {self.purpose})"

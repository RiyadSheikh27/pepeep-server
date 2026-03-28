from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils import timezone
from apps.utils.models import TimeStampedModel
from apps.utils.validators import validate_phone
from .managers import UserManager

# --- User Model -----------------------------------------------------------------------

class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    Custom user model. Phone number is the unique identifier.
    Passwords are unusable by default; auth is OTP-only.
    """
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        OWNER = "owner", "Owner"
        STAFF = "staff", "Staff"
        ADMIN = "admin", "Admin"

    phone = models.CharField(max_length=15, unique=True, db_index=True, validators=[validate_phone])
    country_code = models.CharField(max_length=5, blank=True, default="+966")
    email = models.EmailField(blank=True, null=True, unique=True)
    full_Name = models.CharField(max_length=255, blank=True, default="")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        db_table = "auth_user"

        indexes = [
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return f"{self.phone} ({self.get_role_display()})"
    
    @property
    def is_owner(self):
        return self.role == self.Role.OWNER
    
    @property
    def is_admin_user(self):
        return self.role == self.Role.ADMIN

# --- OTP Verification Model -----------------------------------------------------------------------

class OTPVerification(TimeStampedModel):
    """
    One row per OTP send attempt.
    After successful verify(), `verification_token` is populated and
    returned to the client to prove the phone was verified.
    """
    MAX_ATTEMPTS = 5
    OTP_TTL_SECONDS = 5 * 60  

    class Purpose(models.TextChoices):
        LOGIN = "login", "Login"
        REGISTRATION = "registration", "Registration"
        PHONE_CHANGE = "phone_change", "Phone Change"

    phone = models.CharField(max_length=15, db_index=True)
    country_code = models.CharField(max_length=5, blank=True, default="+966")
    otp_code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.REGISTRATION)
    attempts = models.IntegerField(default=0)
    is_used = models.BooleanField(default=False, db_index=True)
    is_verified = models.BooleanField(default=False, db_index=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(blank=True, null=True)
    verification_token = models.CharField(max_length=64, blank=True, null=True, unique=True)
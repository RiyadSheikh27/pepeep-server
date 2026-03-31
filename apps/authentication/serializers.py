from rest_framework import serializers

from apps.utils.validators import validate_sa_phone
from apps.restaurants.models import Branch, Employee
from .models import User

# --- Shared ------------------------------------------------------------------

class PhoneSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, validators=[validate_sa_phone])

    def validate_phone(self, v):
        return v.replace(" ", "")


# --- CUSTOMER -----------------------------------------------------------------

class CustomerOTPSendSerializer(PhoneSerializer):
    purpose = serializers.ChoiceField(
        choices=["login", "change_phone"],
        default="login",
    )


class CustomerOTPVerifySerializer(PhoneSerializer):
    otp_code = serializers.CharField(min_length=6, max_length=6)

    def validate_otp_code(self, v):
        if not v.isdigit():
            raise serializers.ValidationError("OTP must be 6 digits.")
        return v


class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ["id", "full_name", "username", "email", "phone", "avatar", "created_at"]
        read_only_fields = ["id", "phone", "created_at"]

    def validate_username(self, v):
        qs = User.objects.filter(username=v)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("This username is already taken.")
        return v


class ChangePhoneRequestSerializer(PhoneSerializer):
    """Step 1 of change-phone flow — send OTP to the NEW number."""
    pass


class ChangePhoneVerifySerializer(serializers.Serializer):
    new_phone                = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    otp_code                 = serializers.CharField(min_length=6, max_length=6)
    phone_verification_token = serializers.CharField()

    def validate_new_phone(self, v):
        return v.replace(" ", "")

    def validate_otp_code(self, v):
        if not v.isdigit():
            raise serializers.ValidationError("OTP must be 6 digits.")
        return v


# --- Employee -----------------------------------------------------------------

class EmployeeLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=50)
    password = serializers.CharField(write_only=True)


# --- Owner Auth ---------------------------------------------------------------

class OwnerLoginSerializer(serializers.Serializer):
    phone    = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    password = serializers.CharField(write_only=True)

    def validate_phone(self, v):
        return v.replace(" ", "")


class BranchSerializer(serializers.ModelSerializer):
    """Lightweight — used in login response branch list."""
    restaurant_name = serializers.CharField(source="restaurant.brand_name", read_only=True)

    class Meta:
        model  = Branch
        fields = ["id", "name", "city", "restaurant_name"]


# --- OWNER Registration ---------------------------------------------------

class ShiftSerializer(serializers.Serializer):
    """Single time shift: { "open": "09:00", "close": "22:00" }"""
    open  = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])
    close = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])

    def validate(self, attrs):
        if attrs["open"] >= attrs["close"]:
            raise serializers.ValidationError("Close time must be after open time.")
        return attrs

    def to_representation(self, instance):
        # Store as plain strings so JSONField stays clean
        return {
            "open":  instance["open"].strftime("%H:%M") if hasattr(instance["open"], "strftime") else instance["open"],
            "close": instance["close"].strftime("%H:%M") if hasattr(instance["close"], "strftime") else instance["close"],
        }


class OpeningHoursSerializer(serializers.Serializer):
    """One row per day. Supports up to 3 shifts."""
    DAY_CHOICES = [
        "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "sunday",
    ]

    day     = serializers.ChoiceField(choices=[(d, d.capitalize()) for d in DAY_CHOICES])
    is_open = serializers.BooleanField(default=True)
    shifts  = ShiftSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        if attrs.get("is_open") and not attrs.get("shifts"):
            raise serializers.ValidationError(
                {"shifts": "At least one shift is required when the branch is open."}
            )
        if len(attrs.get("shifts", [])) > 3:
            raise serializers.ValidationError(
                {"shifts": "A maximum of 3 shifts per day is allowed."}
            )
        return attrs


class BranchCreateSerializer(serializers.Serializer):
    """Used in registration Step 4 and add-branch."""
    name          = serializers.CharField(max_length=200)
    city          = serializers.CharField(max_length=100)
    full_address  = serializers.CharField(max_length=300)
    min_order     = serializers.DecimalField(max_digits=8, decimal_places=2)
    opening_hours = OpeningHoursSerializer(many=True, required=False, default=list)

    def validate_opening_hours(self, hours):
        days = [h["day"] for h in hours]
        if len(days) != len(set(days)):
            raise serializers.ValidationError("Duplicate days found in opening hours.")
        return hours


class OwnerRegSubmitSerializer(serializers.Serializer):
    """
    Flat registration form — all steps combined.
    Content-Type: multipart/form-data

    Branches are NOT part of this serializer.
    They are sent as a JSON string in the 'branches' field and
    validated separately in the view using BranchCreateSerializer.
    """

    CATEGORY_CHOICES = [
        ("fast_food",   "Fast Food"),
        ("casual",      "Casual Dining"),
        ("fine_dining", "Fine Dining"),
        ("cafe",        "Café"),
        ("bakery",      "Bakery"),
        ("pizza",       "Pizza"),
        ("sushi",       "Sushi"),
        ("shawarma",    "Shawarma"),
        ("seafood",     "Seafood"),
        ("other",       "Other"),
    ]

    BANK_CHOICES = [
        ("al_rajhi", "Al Rajhi Bank"),
        ("snb",      "Saudi National Bank"),
        ("riyad",    "Riyad Bank"),
        ("samba",    "Samba Financial Group"),
        ("alinma",   "Alinma Bank"),
        ("bsf",      "Banque Saudi Fransi"),
        ("arab",     "Arab National Bank"),
        ("sib",      "Saudi Investment Bank"),
        ("other",    "Other"),
    ]

    # Step 1 — owner info
    full_name                = serializers.CharField(max_length=150)
    phone                    = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    email                    = serializers.EmailField()
    password                 = serializers.CharField(write_only=True, min_length=8)
    phone_verification_token = serializers.CharField()

    # Step 2 — restaurant brand
    legal_name        = serializers.CharField(max_length=200)
    brand_name        = serializers.CharField(max_length=200)
    category          = serializers.ChoiceField(choices=CATEGORY_CHOICES)
    logo              = serializers.ImageField(required=False, allow_null=True)
    short_description = serializers.CharField(max_length=500, required=False, allow_blank=True)

    # Step 3 — legal
    cr_number       = serializers.CharField(max_length=20)
    vat_number      = serializers.CharField(max_length=20)
    cr_document     = serializers.FileField()
    vat_certificate = serializers.FileField()

    # Step 3 — address
    short_address             = serializers.CharField(max_length=200, required=False, allow_blank=True)
    street_name               = serializers.CharField(max_length=200)
    building_number           = serializers.CharField(max_length=20)
    building_secondary_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    district                  = serializers.CharField(max_length=100)
    postal_code               = serializers.CharField(max_length=10)
    unit_number               = serializers.CharField(max_length=20, required=False, allow_blank=True)
    city                      = serializers.CharField(max_length=100)
    country                   = serializers.CharField(max_length=100, default="Saudi Arabia")

    # Step 6 — bank
    bank_name           = serializers.ChoiceField(choices=BANK_CHOICES)
    account_holder_name = serializers.CharField(max_length=200)
    iban                = serializers.CharField(max_length=34)
    bank_iban_pdf       = serializers.FileField()

    def validate_phone(self, v):
        return v.replace(" ", "")

    def validate_iban(self, v):
        v = v.replace(" ", "").upper()
        if not v.startswith("SA") or len(v) != 24:
            raise serializers.ValidationError("Must be a valid Saudi IBAN (SA + 22 digits).")
        return v


# --- OWNER - Staff management ------------------------------------------------------------------------------------------

class CreateEmployeeSerializer(serializers.Serializer):
    username    = serializers.CharField(max_length=50)
    phone       = serializers.CharField(max_length=20, validators=[validate_sa_phone], required=False, allow_blank=True)
    password    = serializers.CharField(write_only=True, min_length=6)
    branch_id   = serializers.UUIDField()
    permissions = serializers.MultipleChoiceField(choices=Employee.ALL_PERMISSIONS, default=list)

    def validate_username(self, v):
        if User.objects.filter(username=v).exists():
            raise serializers.ValidationError("Username already taken.")
        return v

    def validate_branch_id(self, v):
        request = self.context["request"]
        if not Branch.objects.filter(id=v, restaurant__owner=request.user, is_active=True).exists():
            raise serializers.ValidationError("Branch not found or does not belong to you.")
        return v

    def validate_phone(self, v):
        return v.replace(" ", "") if v else v


class EmployeeDetailSerializer(serializers.ModelSerializer):
    username    = serializers.CharField(source="user.username")
    phone       = serializers.CharField(source="user.phone")
    is_active   = serializers.BooleanField(source="user.is_active")
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model  = Employee
        fields = ["id", "username", "phone", "is_active", "branch_name", "permissions", "created_at"]
        read_only_fields = ["id", "created_at"]


# --- ADMIN --------------------------------------------------------------------------------------------

class AdminLoginSerializer(serializers.Serializer):
    phone    = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    password = serializers.CharField(write_only=True)

    def validate_phone(self, v):
        return v.replace(" ", "")


class AdminForgotPasswordSerializer(PhoneSerializer):
    pass


class AdminResetPasswordSerializer(serializers.Serializer):
    phone                    = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    phone_verification_token = serializers.CharField()
    new_password             = serializers.CharField(write_only=True, min_length=8)

    def validate_phone(self, v):
        return v.replace(" ", "")


class AdminProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ["id", "full_name", "username", "email", "phone", "avatar"]
        read_only_fields = ["id"]

    def validate_username(self, v):
        qs = User.objects.filter(username=v)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("Username already taken.")
        return v

    def validate_phone(self, v):
        v = v.replace(" ", "")
        qs = User.objects.filter(phone=v)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError("Phone number already in use.")
        return v

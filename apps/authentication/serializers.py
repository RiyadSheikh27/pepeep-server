import json
from rest_framework import serializers
from apps.utils.validators import validate_sa_phone
from apps.restaurants.models import Branch, Employee
from .models import User

class JSONStringOrListField(serializers.Field):
    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                raise serializers.ValidationError("branches must be valid JSON.")
        if not isinstance(data, list):
            raise serializers.ValidationError("branches must be a list.")
        if len(data) == 0:
            raise serializers.ValidationError("At least one branch is required.")
        s = BranchCreateSerializer(data=data, many=True)
        if not s.is_valid():
            raise serializers.ValidationError(s.errors)
        return s.validated_data

    def to_representation(self, value):
        return value

# ── Shared ────────────────────────────────────────────────────────────────────

class PhoneSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, validators=[validate_sa_phone])

    def validate_phone(self, v):
        return v.replace(" ", "")


# ─────────────────────────────────────────────────────────────────────────────
# CUSTOMER
# ─────────────────────────────────────────────────────────────────────────────

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
    """Step 1 — send OTP to the NEW phone number."""
    pass


class ChangePhoneVerifySerializer(serializers.Serializer):
    new_phone                = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    otp_code                 = serializers.CharField(min_length=6, max_length=6)
    phone_verification_token = serializers.CharField()

    def validate_new_phone(self, v):
        return v.replace(" ", "")


# ─────────────────────────────────────────────────────────────────────────────
# EMPLOYEE
# ─────────────────────────────────────────────────────────────────────────────

class EmployeeLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=50)
    password = serializers.CharField(write_only=True)


# ─────────────────────────────────────────────────────────────────────────────
# OWNER — Login
# ─────────────────────────────────────────────────────────────────────────────

class OwnerLoginSerializer(serializers.Serializer):
    phone    = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    password = serializers.CharField(write_only=True)

    def validate_phone(self, v):
        return v.replace(" ", "")


class BranchSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source="restaurant.name", read_only=True)

    class Meta:
        model  = Branch
        fields = ["id", "name", "city", "restaurant_name"]


# ─────────────────────────────────────────────────────────────────────────────
# OWNER — Registration (6 steps)
# ─────────────────────────────────────────────────────────────────────────────

class OwnerRegStep1Serializer(serializers.Serializer):
    """Step 1: Personal info + phone verification."""
    full_name                = serializers.CharField(max_length=150)
    phone                    = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    email                    = serializers.EmailField()
    phone_verification_token = serializers.CharField()   # obtained after OTP verify

    def validate_phone(self, v):
        return v.replace(" ", "")

    def validate_phone_verification_token(self, v):
        if not v.strip():
            raise serializers.ValidationError("Verification token is required.")
        return v


class OwnerRegStep2Serializer(serializers.Serializer):
    """Step 2: Restaurant brand details."""
    CATEGORY_CHOICES = [
        ("fast_food",    "Fast Food"),
        ("casual",       "Casual Dining"),
        ("fine_dining",  "Fine Dining"),
        ("cafe",         "Café"),
        ("bakery",       "Bakery"),
        ("pizza",        "Pizza"),
        ("sushi",        "Sushi"),
        ("shawarma",     "Shawarma"),
        ("seafood",      "Seafood"),
        ("other",        "Other"),
    ]

    legal_name        = serializers.CharField(max_length=200)
    brand_name        = serializers.CharField(max_length=200)
    category          = serializers.ChoiceField(choices=CATEGORY_CHOICES)
    logo              = serializers.ImageField(required=False, allow_null=True)
    short_description = serializers.CharField(max_length=500, required=False, allow_blank=True)


class OwnerRegStep3Serializer(serializers.Serializer):
    """Step 3: Legal documents + address."""
    cr_number       = serializers.CharField(max_length=20)
    vat_number      = serializers.CharField(max_length=20)
    cr_document     = serializers.FileField()
    vat_certificate = serializers.FileField()
    short_address   = serializers.CharField(max_length=200)
    street_name     = serializers.CharField(max_length=200)
    building_number = serializers.CharField(max_length=20)
    building_secondary_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    district        = serializers.CharField(max_length=100)
    postal_code     = serializers.CharField(max_length=10)
    unit_number     = serializers.CharField(max_length=20, required=False, allow_blank=True)
    city            = serializers.CharField(max_length=100)
    country         = serializers.CharField(max_length=100, default="Saudi Arabia")


class OpeningHoursSerializer(serializers.Serializer):
    """Single day opening hours — supports up to 3 shifts."""
    DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    day     = serializers.ChoiceField(choices=[(d, d.capitalize()) for d in DAYS])
    is_open = serializers.BooleanField(default=True)
    shifts  = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        max_length=3,
        required=False,
        default=list,
    )

    def validate_shifts(self, v):
        for shift in v:
            if "open" not in shift or "close" not in shift:
                raise serializers.ValidationError("Each shift must have 'open' and 'close' times.")
        return v


class BranchCreateSerializer(serializers.Serializer):
    """Single branch definition used in Step 4 / add-branch."""
    name         = serializers.CharField(max_length=200)
    city         = serializers.CharField(max_length=100)
    full_address = serializers.CharField(max_length=300)
    min_order    = serializers.DecimalField(max_digits=8, decimal_places=2)
    opening_hours = OpeningHoursSerializer(many=True)


class OwnerRegStep4Serializer(serializers.Serializer):
    """Step 4: First branch details."""
    branch = BranchCreateSerializer()


class OwnerRegStep6Serializer(serializers.Serializer):
    """Step 6: Bank details."""
    BANK_CHOICES = [
        ("al_rajhi",   "Al Rajhi Bank"),
        ("snb",        "Saudi National Bank"),
        ("riyad",      "Riyad Bank"),
        ("samba",      "Samba Financial Group"),
        ("alinma",     "Alinma Bank"),
        ("bsf",        "Banque Saudi Fransi"),
        ("arab",       "Arab National Bank"),
        ("sib",        "Saudi Investment Bank"),
        ("other",      "Other"),
    ]

    bank_name           = serializers.ChoiceField(choices=BANK_CHOICES)
    account_holder_name = serializers.CharField(max_length=200)
    iban                = serializers.CharField(max_length=34)
    bank_iban_pdf       = serializers.FileField()

    def validate_iban(self, v):
        v = v.replace(" ", "").upper()
        if not v.startswith("SA") or len(v) != 24:
            raise serializers.ValidationError("IBAN must be a valid Saudi IBAN (SA + 22 digits).")
        return v


class OwnerRegSubmitSerializer(serializers.Serializer):
    """
    Final submit — combines all 6 steps.
    The frontend should accumulate data across steps and send everything here.
    Alternatively the backend can use a draft model (OwnerRegistration) and the
    frontend just sends a `registration_id` — see services.py for both paths.
    """
    # Step 1
    full_name                = serializers.CharField(max_length=150)
    phone                    = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    email                    = serializers.EmailField()
    phone_verification_token = serializers.CharField()
    password                 = serializers.CharField(write_only=True, min_length=8)

    # Step 2
    legal_name        = serializers.CharField(max_length=200)
    brand_name        = serializers.CharField(max_length=200)
    category          = serializers.CharField(max_length=50)
    logo              = serializers.ImageField(required=False, allow_null=True)
    short_description = serializers.CharField(max_length=500, required=False, allow_blank=True)

    # Step 3
    cr_number       = serializers.CharField(max_length=20)
    vat_number      = serializers.CharField(max_length=20)
    cr_document     = serializers.FileField()
    vat_certificate = serializers.FileField()
    short_address   = serializers.CharField(max_length=200)
    street_name     = serializers.CharField(max_length=200)
    building_number = serializers.CharField(max_length=20)
    building_secondary_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    district        = serializers.CharField(max_length=100)
    postal_code     = serializers.CharField(max_length=10)
    unit_number     = serializers.CharField(max_length=20, required=False, allow_blank=True)
    city            = serializers.CharField(max_length=100)
    country         = serializers.CharField(max_length=100, default="Saudi Arabia")

    # Step 6
    bank_name           = serializers.CharField(max_length=50)
    account_holder_name = serializers.CharField(max_length=200)
    iban                = serializers.CharField(max_length=34)
    bank_iban_pdf       = serializers.FileField()

    # Branches (collected across steps 4-5, at least one required)
    branches = JSONStringOrListField()

    def validate_phone(self, v):
        return v.replace(" ", "")

    def validate_iban(self, v):
        v = v.replace(" ", "").upper()
        if not v.startswith("SA") or len(v) != 24:
            raise serializers.ValidationError("Must be a valid Saudi IBAN (SA + 22 digits).")
        return v

    def to_internal_value(self, data):
        data = data.copy()
        if "branches" in data and isinstance(data["branches"], str):
            import json
            try:
                data["branches"] = json.loads(data["branches"])
            except json.JSONDecodeError:
                raise serializers.ValidationError({"branches": ["Invalid JSON."]})
        return super().to_internal_value(data)


# ─────────────────────────────────────────────────────────────────────────────
# OWNER — Staff management
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────────────────────────────────────

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
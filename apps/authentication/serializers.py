from rest_framework import serializers

from apps.utils.validators import validate_sa_phone
from apps.restaurants.models import Branch, Employee, BranchOpeningHours
from .models import User


# ---------------------------------------------------------------------------
# Shared / Mixins
# ---------------------------------------------------------------------------

class PhoneSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, validators=[validate_sa_phone])

    def validate_phone(self, v):
        return v.replace(" ", "")


class OTPCodeMixin(serializers.Serializer):
    otp_code = serializers.CharField(min_length=6, max_length=6)

    def validate_otp_code(self, v):
        if not v.isdigit():
            raise serializers.ValidationError("OTP must be 6 digits.")
        return v


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class CustomerOTPSendSerializer(PhoneSerializer):
    purpose = serializers.ChoiceField(choices=["login", "change_phone"], default="login")


class CustomerOTPVerifySerializer(PhoneSerializer, OTPCodeMixin):
    pass


class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
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


class ChangePhoneVerifySerializer(OTPCodeMixin):
    new_phone                = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    phone_verification_token = serializers.CharField()

    def validate_new_phone(self, v):
        return v.replace(" ", "")


# ---------------------------------------------------------------------------
# Employee
# ---------------------------------------------------------------------------

class EmployeeLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=50)
    password = serializers.CharField(write_only=True)


class EmployeeDetailSerializer(serializers.ModelSerializer):
    username    = serializers.CharField(source="user.username")
    phone       = serializers.CharField(source="user.phone")
    is_active   = serializers.BooleanField(source="user.is_active")
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Employee
        fields = ["id", "username", "phone", "is_active", "branch_name", "permissions", "created_at"]
        read_only_fields = ["id", "created_at"]


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
        if not Branch.objects.filter(id=v, restaurant__owner=self.context["request"].user, is_active=True).exists():
            raise serializers.ValidationError("Branch not found or does not belong to you.")
        return v

    def validate_phone(self, v):
        return v.replace(" ", "") if v else v


# ---------------------------------------------------------------------------
# Owner — Auth
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Opening Hours (shared between registration and owner profile update)
# ---------------------------------------------------------------------------

class ShiftSerializer(serializers.Serializer):
    open  = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])
    close = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])

    def validate(self, attrs):
        if attrs["open"] >= attrs["close"]:
            raise serializers.ValidationError("Close time must be after open time.")
        return attrs

    def to_representation(self, instance):
        fmt = lambda t: t.strftime("%H:%M") if hasattr(t, "strftime") else t
        return {"open": fmt(instance["open"]), "close": fmt(instance["close"])}


class OpeningHoursSerializer(serializers.Serializer):
    DAY_CHOICES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    day     = serializers.ChoiceField(choices=[(d, d.capitalize()) for d in DAY_CHOICES])
    is_open = serializers.BooleanField(default=True)
    shifts  = ShiftSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        if attrs.get("is_open") and not attrs.get("shifts"):
            raise serializers.ValidationError({"shifts": "At least one shift is required when the branch is open."})
        if len(attrs.get("shifts", [])) > 3:
            raise serializers.ValidationError({"shifts": "A maximum of 3 shifts per day is allowed."})
        return attrs


class OpeningHoursReadSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BranchOpeningHours
        fields = ["id", "day", "is_open", "shifts"]


class BranchCreateSerializer(serializers.Serializer):
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


# ---------------------------------------------------------------------------
# Owner — Registration
# ---------------------------------------------------------------------------

CATEGORY_CHOICES = [
    ("fast_food", "Fast Food"), ("casual", "Casual Dining"), ("fine_dining", "Fine Dining"),
    ("cafe", "Café"), ("bakery", "Bakery"), ("pizza", "Pizza"),
    ("sushi", "Sushi"), ("shawarma", "Shawarma"), ("seafood", "Seafood"), ("other", "Other"),
]

BANK_CHOICES = [
    ("al_rajhi", "Al Rajhi Bank"), ("snb", "Saudi National Bank"), ("riyad", "Riyad Bank"),
    ("samba", "Samba Financial Group"), ("alinma", "Alinma Bank"), ("bsf", "Banque Saudi Fransi"),
    ("arab", "Arab National Bank"), ("sib", "Saudi Investment Bank"), ("other", "Other"),
]


class OwnerRegSubmitSerializer(serializers.Serializer):
    """
    Flat registration form — all steps combined.
    Content-Type: multipart/form-data
    Branches are sent as a JSON string in the 'branches' field,
    validated separately in the view using BranchCreateSerializer.
    """
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

    # Step 4 — bank
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


# ---------------------------------------------------------------------------
# Owner — Profile & Restaurant Update
# ---------------------------------------------------------------------------

class OwnerProfileSerializer(serializers.ModelSerializer):
    """Read/update owner's personal info (full_name, email, avatar)."""
    class Meta:
        model  = User
        fields = ["id", "full_name", "email", "phone", "avatar", "created_at"]
        read_only_fields = ["id", "phone", "created_at"]


class RestaurantUpdateSerializer(serializers.Serializer):
    """Partial update for restaurant brand + legal + address info."""
    # Brand
    brand_name        = serializers.CharField(max_length=200, required=False)
    category          = serializers.ChoiceField(choices=CATEGORY_CHOICES, required=False)
    logo              = serializers.ImageField(required=False, allow_null=True)
    short_description = serializers.CharField(max_length=500, required=False, allow_blank=True)

    # Legal
    cr_number       = serializers.CharField(max_length=20, required=False)
    vat_number      = serializers.CharField(max_length=20, required=False)
    cr_document     = serializers.FileField(required=False, allow_null=True)
    vat_certificate = serializers.FileField(required=False, allow_null=True)

    # Address
    short_address             = serializers.CharField(max_length=200, required=False, allow_blank=True)
    street_name               = serializers.CharField(max_length=200, required=False)
    building_number           = serializers.CharField(max_length=20, required=False)
    building_secondary_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    district                  = serializers.CharField(max_length=100, required=False)
    postal_code               = serializers.CharField(max_length=10, required=False)
    unit_number               = serializers.CharField(max_length=20, required=False, allow_blank=True)
    city                      = serializers.CharField(max_length=100, required=False)
    country                   = serializers.CharField(max_length=100, required=False)


class BankDetailUpdateSerializer(serializers.Serializer):
    bank_name           = serializers.ChoiceField(choices=BANK_CHOICES, required=False)
    account_holder_name = serializers.CharField(max_length=200, required=False)
    iban                = serializers.CharField(max_length=34, required=False)
    bank_iban_pdf       = serializers.FileField(required=False, allow_null=True)

    def validate_iban(self, v):
        v = v.replace(" ", "").upper()
        if not v.startswith("SA") or len(v) != 24:
            raise serializers.ValidationError("Must be a valid Saudi IBAN (SA + 22 digits).")
        return v


class BranchDetailSerializer(serializers.ModelSerializer):
    opening_hours = OpeningHoursReadSerializer(many=True, read_only=True)
    is_active     = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Branch
        fields = ["id", "name", "city", "full_address", "min_order", "is_active", "opening_hours"]


class BranchUpdateSerializer(serializers.Serializer):
    """Partial update for an existing branch (name, city, address, min_order)."""
    name         = serializers.CharField(max_length=200, required=False)
    city         = serializers.CharField(max_length=100, required=False)
    full_address = serializers.CharField(max_length=300, required=False)
    min_order    = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class AdminLoginSerializer(serializers.Serializer):
    phone    = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    password = serializers.CharField(write_only=True)

    def validate_phone(self, v):
        return v.replace(" ", "")


class AdminForgotPasswordSerializer(PhoneSerializer):
    pass


class AdminResetPasswordSerializer(PhoneSerializer):
    phone_verification_token = serializers.CharField()
    new_password             = serializers.CharField(write_only=True, min_length=8)


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
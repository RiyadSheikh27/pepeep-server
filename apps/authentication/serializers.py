from rest_framework import serializers
from apps.utils.validators import validate_sa_phone
from apps.restaurants.models import Branch, Employee
from .models import User


# --- Shared ---------------------------------------------------------------

class PhoneSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20, validators=[validate_sa_phone])

    def validate_phone(self, v):
        return v.replace(" ", "")


# --- Customer ------------------------------------------------------------

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
    new_phone             = serializers.CharField(max_length=20, validators=[validate_sa_phone])
    otp_code              = serializers.CharField(min_length=6, max_length=6)
    phone_verification_token = serializers.CharField()

    def validate_new_phone(self, v):
        return v.replace(" ", "")


# --- Employee ---------------------------------------------------------------

class EmployeeLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=50)
    password = serializers.CharField(write_only=True)


# --- Owner -----------------------------------------------------------------

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


# --- Owner — create employee --------------------------------------------------

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


# --- Admin ------------------------------------------------------------------------------------------

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

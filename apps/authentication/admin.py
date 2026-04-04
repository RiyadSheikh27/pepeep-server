from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django import forms

from .models import User, OTPVerification


# Custom User Change Form (IMPORTANT FIX)
class UserChangeForm(forms.ModelForm):
    password = forms.CharField(required=False)

    class Meta:
        model = User
        fields = "__all__"

    def clean_password(self):
        return self.initial.get("password")  # prevents None issue


# Custom User Creation Form
class UserCreationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("phone", "password")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


# Admin Config
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = (
        "id",
        "phone",
        "username",
        "role",
        "is_active",
        "is_staff",
        "created_at",
    )

    list_filter = ("role", "is_active", "is_staff")

    search_fields = ("phone", "username", "email")
    ordering = ("-created_at",)

    readonly_fields = ("created_at", "updated_at", "last_login")

    # 🔥 VERY IMPORTANT (fixes your error)
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Personal Info", {"fields": ("username", "email", "full_name", "avatar")}),
        ("Permissions", {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("phone", "password"),
        }),
    )


# OTP Admin
@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = (
        "phone",
        "purpose",
        "is_verified",
        "is_used",
        "attempts",
        "expires_at",
        "created_at",
    )

    list_filter = ("purpose", "is_verified", "is_used")
    search_fields = ("phone",)
    ordering = ("-created_at",)

    readonly_fields = ("created_at", "updated_at")
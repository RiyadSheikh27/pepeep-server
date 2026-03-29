from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OTPVerification


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display    = ["phone", "username", "full_name", "role", "is_active", "created_at"]
    list_filter     = ["role", "is_active", "is_phone_verified"]
    search_fields   = ["phone", "username", "full_name", "email"]
    ordering        = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]

    fieldsets = (
        (None,          {"fields": ("phone", "username", "password")}),
        ("Info",        {"fields": ("full_name", "email", "avatar")}),
        ("Access",      {"fields": ("role", "is_active", "is_staff", "is_superuser",
                                    "is_phone_verified", "groups", "user_permissions")}),
        ("Timestamps",  {"fields": ("created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": (
            "phone", "username", "full_name", "role", "password1", "password2"
        )}),
    )


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display  = ["phone", "purpose", "is_verified", "is_used", "attempts", "expires_at", "created_at"]
    list_filter   = ["purpose", "is_verified", "is_used"]
    search_fields = ["phone"]
    readonly_fields = ["verification_token", "created_at"]

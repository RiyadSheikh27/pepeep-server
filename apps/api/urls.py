from django.urls import path
from apps.authentication.views import (
    # Customer
    CustomerOTPSendView, CustomerLoginView,
    CustomerProfileView,
    CustomerChangePhoneRequestView, CustomerChangePhoneVerifyView,
    # Employee
    EmployeeLoginView,
    # Owner — registration
    OwnerRegOTPSendView, OwnerRegOTPVerifyView, OwnerRegSubmitView,
    # Owner — login & branches
    OwnerLoginView, OwnerBranchListView,
    # Owner — staff
    OwnerStaffListCreateView, OwnerStaffDetailView,
    # Admin
    AdminLoginView, AdminForgotPasswordView,
    AdminVerifyOTPView, AdminResetPasswordView,
    AdminProfileView,
    # Shared
    LogoutView,
)

urlpatterns = [

    # ── Customer ──────────────────────────────────────────────────────────────
    path("customer/auth/otp/send/",            CustomerOTPSendView.as_view()),
    path("customer/auth/login/",               CustomerLoginView.as_view()),
    path("customer/profile/",                  CustomerProfileView.as_view()),
    path("customer/auth/change-phone/request/", CustomerChangePhoneRequestView.as_view()),
    path("customer/auth/change-phone/verify/",  CustomerChangePhoneVerifyView.as_view()),

    # ── Employee ──────────────────────────────────────────────────────────────
    path("employee/auth/login/",               EmployeeLoginView.as_view()),

    # ── Owner — Registration ──────────────────────────────────────────────────
    path("owner/auth/register/otp/send/",      OwnerRegOTPSendView.as_view()),
    path("owner/auth/register/otp/verify/",    OwnerRegOTPVerifyView.as_view()),
    path("owner/auth/register/submit/",        OwnerRegSubmitView.as_view()),

    # ── Owner — Login & Branches ──────────────────────────────────────────────
    path("owner/auth/login/",                  OwnerLoginView.as_view()),
    path("owner/branches/",                    OwnerBranchListView.as_view()),

    # ── Owner — Staff ─────────────────────────────────────────────────────────
    path("owner/staff/",                       OwnerStaffListCreateView.as_view()),
    path("owner/staff/<uuid:pk>/",             OwnerStaffDetailView.as_view()),

    # ── Admin ─────────────────────────────────────────────────────────────────
    path("admin/auth/login/",                  AdminLoginView.as_view()),
    path("admin/auth/forgot-password/",        AdminForgotPasswordView.as_view()),
    path("admin/auth/otp/verify/",             AdminVerifyOTPView.as_view()),
    path("admin/auth/reset-password/",         AdminResetPasswordView.as_view()),
    path("admin/profile/",                     AdminProfileView.as_view()),

    # ── Shared ────────────────────────────────────────────────────────────────
    path("auth/logout/",                       LogoutView.as_view()),
]
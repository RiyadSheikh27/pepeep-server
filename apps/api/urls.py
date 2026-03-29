from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from apps.authentication.views import (
    # Customer
    CustomerOTPSendView, CustomerLoginView,
    CustomerProfileView,
    CustomerChangePhoneRequestView, CustomerChangePhoneVerifyView,
    # Employee
    EmployeeLoginView,
    # Owner
    OwnerLoginView, OwnerBranchListView,
    OwnerStaffListCreateView, OwnerStaffDetailView,
    # Admin
    AdminLoginView, AdminForgotPasswordView,
    AdminVerifyOTPView, AdminResetPasswordView,
    AdminProfileView,
    # Shared
    LogoutView,
)

app_name = "authentication"

urlpatterns = [

    # --- Customer ------------------------------------------------------------
    path("customer/auth/otp/send/",            CustomerOTPSendView.as_view(),            name="customer-otp-send"),
    path("customer/auth/login/",               CustomerLoginView.as_view(),              name="customer-login"),
    path("customer/profile/",                  CustomerProfileView.as_view(),            name="customer-profile"),
    path("customer/auth/change-phone/request/",CustomerChangePhoneRequestView.as_view(), name="customer-change-phone-request"),
    path("customer/auth/change-phone/verify/", CustomerChangePhoneVerifyView.as_view(),  name="customer-change-phone-verify"),

    # --- Employee ------------------------------------------------------------
    path("employee/auth/login/", EmployeeLoginView.as_view(), name="employee-login"),

    # --- Owner ---------------------------------------------------------------
    path("owner/auth/login/",     OwnerLoginView.as_view(),           name="owner-login"),
    path("owner/branches/",       OwnerBranchListView.as_view(),      name="owner-branches"),
    path("owner/staff/",          OwnerStaffListCreateView.as_view(), name="owner-staff-list-create"),
    path("owner/staff/<uuid:pk>/",OwnerStaffDetailView.as_view(),     name="owner-staff-detail"),

    # --- Admin ---------------------------------------------------------------
    path("admin/auth/login/",           AdminLoginView.as_view(),          name="admin-login"),
    path("admin/auth/forgot-password/", AdminForgotPasswordView.as_view(), name="admin-forgot-password"),
    path("admin/auth/otp/verify/",      AdminVerifyOTPView.as_view(),      name="admin-otp-verify"),
    path("admin/auth/reset-password/",  AdminResetPasswordView.as_view(),  name="admin-reset-password"),
    path("admin/profile/",              AdminProfileView.as_view(),         name="admin-profile"),

    # --- Shared ---------------------------------------------------------------
    path("auth/logout/",        LogoutView.as_view(),        name="logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(),  name="token-refresh"),
]

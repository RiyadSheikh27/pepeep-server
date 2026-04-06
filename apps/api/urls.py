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
    # Owner — profile & restaurant
    OwnerProfileView, OwnerRestaurantView, OwnerBankDetailView,
    OwnerBranchManageView, OwnerBranchDetailView, OwnerBranchOpeningHoursView,
    # Owner — staff
    OwnerStaffListCreateView, OwnerStaffDetailView,
    # Admin — auth
    AdminLoginView, AdminForgotPasswordView,
    AdminVerifyOTPView, AdminResetPasswordView,
    AdminProfileView,
    # Admin — approvals
    AdminRestaurantApproveView, AdminRestaurantRejectView,
    AdminBranchApproveView, AdminBranchRejectView,
    # Admin — customers
    AdminCustomerListView, AdminCustomerDetailView,
    # Admin — owners
    AdminOwnerListView, AdminOwnerDetailView,
    # Admin — employees
    AdminEmployeeListView, AdminEmployeeDetailView,
    # Admin — restaurants
    AdminRestaurantListView, AdminRestaurantDetailView,
    # Admin — branches
    AdminBranchListView, AdminBranchDetailView,
    # Shared
    LogoutView,
)

from apps.food_menus.views import (
    MenuCategoryListCreateView,
    MenuCategoryDetailView,
    MenuItemListCreateView,
    MenuItemDetailView,
    MenuItemToggleAvailabilityView,
    ModifierGroupListCreateView,
    ModifierGroupDetailView,
    ModifierOptionCreateView,
    ModifierOptionDetailView,
)

auth_urlpatterns = [

    # --- Customer ---------------------------------------------------------------
    path("customer/auth/otp/send/", CustomerOTPSendView.as_view()),
    path("customer/auth/login/", CustomerLoginView.as_view()),
    path("customer/profile/", CustomerProfileView.as_view()),
    path("customer/auth/change-phone/request/", CustomerChangePhoneRequestView.as_view()),
    path("customer/auth/change-phone/verify/", CustomerChangePhoneVerifyView.as_view()),

    # --- Employee ----------------------------------------------------------------
    path("employee/auth/login/", EmployeeLoginView.as_view()),

    # --- Owner - Registration ----------------------------------------------------
    path("owner/auth/register/otp/send/", OwnerRegOTPSendView.as_view()),
    path("owner/auth/register/otp/verify/", OwnerRegOTPVerifyView.as_view()),
    path("owner/auth/register/submit/", OwnerRegSubmitView.as_view()),

    # --- Owner - Login & Branches -------------------------------------------------
    path("owner/auth/login/", OwnerLoginView.as_view()),
    path("owner/branches/", OwnerBranchListView.as_view()),

    # --- Owner - Profile & Restaurant ---------------------------------------------
    path("owner/profile/", OwnerProfileView.as_view()),
    path("owner/restaurant/", OwnerRestaurantView.as_view()),
    path("owner/restaurant/bank/", OwnerBankDetailView.as_view()),
    path("owner/restaurant/branches/", OwnerBranchManageView.as_view()),
    path("owner/restaurant/branches/<uuid:pk>/", OwnerBranchDetailView.as_view()),
    path("owner/restaurant/branches/<uuid:pk>/opening-hours/", OwnerBranchOpeningHoursView.as_view()),

    # --- Owner - Staff -------------------------------------------------------------
    path("owner/staff/", OwnerStaffListCreateView.as_view()),
    path("owner/staff/<uuid:pk>/", OwnerStaffDetailView.as_view()),

    # --- Admin - Auth --------------------------------------------------------------
    path("admin/auth/login/", AdminLoginView.as_view()),
    path("admin/auth/forgot-password/", AdminForgotPasswordView.as_view()),
    path("admin/auth/otp/verify/", AdminVerifyOTPView.as_view()),
    path("admin/auth/reset-password/", AdminResetPasswordView.as_view()),
    path("admin/profile/", AdminProfileView.as_view()),

    # --- Admin - Customers ---------------------------------------------------------
    path("admin/customers/", AdminCustomerListView.as_view()),
    path("admin/customers/<uuid:pk>/", AdminCustomerDetailView.as_view()),

    # --- Admin - Owners ------------------------------------------------------------
    path("admin/owners/", AdminOwnerListView.as_view()),
    path("admin/owners/<uuid:pk>/", AdminOwnerDetailView.as_view()),

    # --- Admin - Employees ---------------------------------------------------------
    path("admin/employees/", AdminEmployeeListView.as_view()),
    path("admin/employees/<uuid:pk>/", AdminEmployeeDetailView.as_view()),

    # --- Admin - Restaurants -------------------------------------------------------
    path("admin/restaurants/", AdminRestaurantListView.as_view()),
    path("admin/restaurants/<uuid:pk>/", AdminRestaurantDetailView.as_view()),
    path("admin/restaurants/<uuid:pk>/approve/", AdminRestaurantApproveView.as_view()),
    path("admin/restaurants/<uuid:pk>/reject/", AdminRestaurantRejectView.as_view()),

    # --- Admin - Branches ----------------------------------------------------------
    path("admin/branches/", AdminBranchListView.as_view()),
    path("admin/branches/<uuid:pk>/", AdminBranchDetailView.as_view()),
    path("admin/branches/<uuid:pk>/approve/", AdminBranchApproveView.as_view()),
    path("admin/branches/<uuid:pk>/reject/", AdminBranchRejectView.as_view()),

    # --- Shared --------------------------------------------------------------------
    path("auth/logout/", LogoutView.as_view()),
]

menu_urlpatterns = [

    # --- Categories ----------------------------------------------------------------
    path("menu/branches/<uuid:branch_id>/categories/", MenuCategoryListCreateView.as_view()),
    path("menu/branches/<uuid:branch_id>/categories/<uuid:category_id>/", MenuCategoryDetailView.as_view()),

    # --- Items ---------------------------------------------------------------------
    path("menu/branches/<uuid:branch_id>/items/", MenuItemListCreateView.as_view()),
    path("menu/branches/<uuid:branch_id>/items/<uuid:item_id>/", MenuItemDetailView.as_view()),
    path("menu/branches/<uuid:branch_id>/items/<uuid:item_id>/toggle-availability/", MenuItemToggleAvailabilityView.as_view()),

    # --- Modifier Groups -----------------------------------------------------------
    path("menu/branches/<uuid:branch_id>/items/<uuid:item_id>/groups/", ModifierGroupListCreateView.as_view()),
    path("menu/branches/<uuid:branch_id>/items/<uuid:item_id>/groups/<uuid:group_id>/", ModifierGroupDetailView.as_view()),

    # --- Modifier Options ----------------------------------------------------------
    path("menu/branches/<uuid:branch_id>/items/<uuid:item_id>/groups/<uuid:group_id>/options/", ModifierOptionCreateView.as_view()),
    path("menu/branches/<uuid:branch_id>/items/<uuid:item_id>/groups/<uuid:group_id>/options/<uuid:option_id>/", ModifierOptionDetailView.as_view()),
]

urlpatterns = [
    *auth_urlpatterns,
    *menu_urlpatterns,
]

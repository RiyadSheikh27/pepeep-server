from rest_framework.permissions import BasePermission
from django.conf import settings

# --- Permission Constants ----------------------------------------------------------------

class Permissions:
    """Define all available permissions as constants."""

    # Menu permissions
    MENU_VIEW = "menu.view"
    MENU_CREATE = "menu.create"
    MENU_EDIT = "menu.edit"
    MENU_DELETE = "menu.delete"

    # Restaurant permissions
    RESTAURANT_VIEW = "restaurant.view"
    RESTAURANT_CREATE = "restaurant.create"
    RESTAURANT_EDIT = "restaurant.edit"
    RESTAURANT_DELETE = "restaurant.delete"

    # Branch permissions
    BRANCH_VIEW = "branch.view"
    BRANCH_CREATE = "branch.create"
    BRANCH_EDIT = "branch.edit"
    BRANCH_DELETE = "branch.delete"

    # Staff permissions
    STAFF_VIEW = "staff.view"
    STAFF_CREATE = "staff.create"
    STAFF_EDIT = "staff.edit"
    STAFF_DELETE = "staff.delete"

    # Customer permissions
    CUSTOMER_VIEW = "customer.view"
    CUSTOMER_EDIT = "customer.edit"

    # Admin permissions
    ADMIN_VIEW = "admin.view"
    ADMIN_EDIT = "admin.edit"

    # All permissions grouped
    ALL_PERMISSIONS = [
        MENU_VIEW, MENU_CREATE, MENU_EDIT, MENU_DELETE,
        RESTAURANT_VIEW, RESTAURANT_CREATE, RESTAURANT_EDIT, RESTAURANT_DELETE,
        BRANCH_VIEW, BRANCH_CREATE, BRANCH_EDIT, BRANCH_DELETE,
        STAFF_VIEW, STAFF_CREATE, STAFF_EDIT, STAFF_DELETE,
        CUSTOMER_VIEW, CUSTOMER_EDIT,
        ADMIN_VIEW, ADMIN_EDIT,
    ]

    # Permission groups for convenience
    MENU_PERMISSIONS = [MENU_VIEW, MENU_CREATE, MENU_EDIT, MENU_DELETE]
    RESTAURANT_PERMISSIONS = [RESTAURANT_VIEW, RESTAURANT_CREATE, RESTAURANT_EDIT, RESTAURANT_DELETE]
    BRANCH_PERMISSIONS = [BRANCH_VIEW, BRANCH_CREATE, BRANCH_EDIT, BRANCH_DELETE]
    STAFF_PERMISSIONS = [STAFF_VIEW, STAFF_CREATE, STAFF_EDIT, STAFF_DELETE]


# --- Role-based Permissions --------------------------------------------------------------

def _is_role(role):
    """Factory for role-based permissions."""
    class RolePermission(BasePermission):
        message = f"Access restricted to {role} accounts."
        def has_permission(self, request, view):
            return bool(
                request.user
                and request.user.is_authenticated
                and request.user.role == role
            )
    RolePermission.__name__ = f"Is{role.capitalize()}"
    return RolePermission


IsCustomer = _is_role("customer")
IsEmployee = _is_role("employee")
IsOwner = _is_role("owner")
IsAdmin = _is_role("admin")


class IsOwnerOrAdmin(BasePermission):
    """Allow access to owners or admins."""
    message = "Owner or admin access required."
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ("owner", "admin")
        )


# --- Custom Permissions -----------------------------------------------------------------

class HasPermission(BasePermission):
    """
    Check if user has a specific permission.
    Usage: HasPermission("menu.view") or HasPermission(["menu.view", "menu.edit"])
    """
    def __init__(self, permissions):
        self.permissions = permissions if isinstance(permissions, list) else [permissions]

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Admins and owners have all permissions
        if request.user.role in ("admin", "owner"):
            return True

        # Check if user has any of the required permissions
        user_permissions = request.user.permissions or []
        return any(perm in user_permissions for perm in self.permissions)

    @property
    def message(self):
        perms = ", ".join(self.permissions)
        return f"Required permission(s): {perms}"


class HasAnyPermission(BasePermission):
    """
    Check if user has ANY of the specified permissions.
    Usage: HasAnyPermission(["menu.view", "restaurant.view"])
    """
    def __init__(self, permissions):
        self.permissions = permissions

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Admins and owners have all permissions
        if request.user.role in ("admin", "owner"):
            return True

        # Check if user has any of the permissions
        user_permissions = request.user.permissions or []
        return any(perm in user_permissions for perm in self.permissions)

    @property
    def message(self):
        perms = ", ".join(self.permissions)
        return f"Required any of these permissions: {perms}"


class HasAllPermissions(BasePermission):
    """
    Check if user has ALL of the specified permissions.
    Usage: HasAllPermissions(["menu.view", "menu.edit"])
    """
    def __init__(self, permissions):
        self.permissions = permissions

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Admins and owners have all permissions
        if request.user.role in ("admin", "owner"):
            return True

        # Check if user has all permissions
        user_permissions = request.user.permissions or []
        return all(perm in user_permissions for perm in self.permissions)

    @property
    def message(self):
        perms = ", ".join(self.permissions)
        return f"Required all of these permissions: {perms}"


# --- Convenience Permission Classes -----------------------------------------------------

# Menu permissions
class CanViewMenu(HasPermission):
    def __init__(self):
        super().__init__(Permissions.MENU_VIEW)

class CanManageMenu(HasAllPermissions):
    def __init__(self):
        super().__init__([Permissions.MENU_VIEW, Permissions.MENU_EDIT])

# Restaurant permissions
class CanViewRestaurant(HasPermission):
    def __init__(self):
        super().__init__(Permissions.RESTAURANT_VIEW)

class CanManageRestaurant(HasAllPermissions):
    def __init__(self):
        super().__init__([Permissions.RESTAURANT_VIEW, Permissions.RESTAURANT_EDIT])

# Branch permissions
class CanViewBranch(HasPermission):
    def __init__(self):
        super().__init__(Permissions.BRANCH_VIEW)

class CanManageBranch(HasAllPermissions):
    def __init__(self):
        super().__init__([Permissions.BRANCH_VIEW, Permissions.BRANCH_EDIT])

# Staff permissions
class CanViewStaff(HasPermission):
    def __init__(self):
        super().__init__(Permissions.STAFF_VIEW)

class CanManageStaff(HasAllPermissions):
    def __init__(self):
        super().__init__([Permissions.STAFF_VIEW, Permissions.STAFF_EDIT])

# Combined permissions for employees
class EmployeeMenuAccess(HasAnyPermission):
    """Employee can view or manage menu."""
    def __init__(self):
        super().__init__(Permissions.MENU_PERMISSIONS)

class EmployeeRestaurantAccess(HasAnyPermission):
    """Employee can view or manage restaurant."""
    def __init__(self):
        super().__init__(Permissions.RESTAURANT_PERMISSIONS)

class EmployeeBranchAccess(HasAnyPermission):
    """Employee can view or manage branches."""
    def __init__(self):
        super().__init__(Permissions.BRANCH_PERMISSIONS)

class EmployeeStaffAccess(HasAnyPermission):
    """Employee can view or manage staff."""
    def __init__(self):
        super().__init__(Permissions.STAFF_PERMISSIONS)


# --- Utility Functions ------------------------------------------------------------------

def user_has_permission(user, permission):
    """Check if a user has a specific permission."""
    if not user or not user.is_authenticated:
        return False

    # Admins and owners have all permissions
    if user.role in ("admin", "owner"):
        return True

    user_permissions = user.permissions or []
    return permission in user_permissions

def user_has_any_permission(user, permissions):
    """Check if a user has any of the specified permissions."""
    if not user or not user.is_authenticated:
        return False

    # Admins and owners have all permissions
    if user.role in ("admin", "owner"):
        return True

    user_permissions = user.permissions or []
    return any(perm in user_permissions for perm in permissions)

def user_has_all_permissions(user, permissions):
    """Check if a user has all of the specified permissions."""
    if not user or not user.is_authenticated:
        return False

    # Admins and owners have all permissions
    if user.role in ("admin", "owner"):
        return True

    user_permissions = user.permissions or []
    return all(perm in user_permissions for perm in permissions)
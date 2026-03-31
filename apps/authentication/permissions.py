from rest_framework.permissions import BasePermission

def _is(role):
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


IsCustomer = _is("customer")
IsEmployee = _is("employee")
IsOwner = _is("owner")
IsAdmin = _is("admin")


class IsOwnerOrAdmin(BasePermission):
    message = "Owner or admin access required."
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ("owner", "admin")
        )
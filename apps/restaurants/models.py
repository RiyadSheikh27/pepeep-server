from django.db import models
from apps.utils.models import TimeStampedModel


class Restaurant(TimeStampedModel):
    owner = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="restaurants",
    )
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "restaurants"

    def __str__(self):
        return self.name


class Branch(TimeStampedModel):
    restaurant = models.ForeignKey(
        Restaurant, on_delete=models.CASCADE, related_name="branches"
    )
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "branches"

    def __str__(self):
        return f"{self.restaurant.name} — {self.name}"


class Employee(TimeStampedModel):
    """
    Links a User(role=employee) to a branch.
    Created by the restaurant owner.
    """

    class Permission(models.TextChoices):
        DASHBOARD = "dashboard", "View Dashboard"
        EDIT_MENU = "edit_menu", "Edit Menu"
        CONFIRM_ORDER = "confirm_order", "Confirm Orders"
        VIEW_REPORTS = "view_reports", "View Reports"
        MANAGE_STAFF = "manage_staff", "Manage Staff"

    ALL_PERMISSIONS = [p.value for p in Permission]

    user = models.OneToOneField(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="employees")
    permissions = models.JSONField(default=list)
    created_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_employees",
    )

    class Meta:
        db_table = "employees"

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions

    def __str__(self):
        return f"{self.user.username} @ {self.branch}"

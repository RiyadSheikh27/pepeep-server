from django.contrib import admin
from .models import Restaurant, Branch, Employee

@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display  = ["name", "owner", "is_active", "created_at"]
    search_fields = ["name", "owner__phone"]

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display  = ["name", "restaurant", "city", "is_active"]
    search_fields = ["name", "restaurant__name"]
    list_filter   = ["is_active"]

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display  = ["user", "branch", "created_at"]
    search_fields = ["user__username", "branch__name"]
    list_select_related = ["user", "branch", "branch__restaurant"]

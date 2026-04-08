from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Restaurant,
    Branch,
    BranchOpeningHours,
    RestaurantBankDetail,
    Employee,
    RestaurantCategory,
)


@admin.register(Restaurant)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = [
        'brand_name',
        'owner',
        'category',
        'status',
        'is_active',
        'created_at',
    ]
    list_filter = ['status', 'category', 'is_active', 'created_at']
    search_fields = ['brand_name', 'legal_name', 'owner__email', 'owner__username']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = [
        ('Basic Information', {
            'fields': [
                'owner',
                'legal_name',
                'brand_name',
                'category',
                'logo',
                'short_description',
            ]
        }),
        ('Legal Documents', {
            'fields': [
                'cr_number',
                'vat_number',
                'cr_document',
                'vat_certificate',
            ]
        }),
        ('Address & Location', {
            'fields': [
                'short_address',
                'street_name',
                'building_number',
                'building_secondary_number',
                'unit_number',
                'district',
                'city',
                'postal_code',
                'country',
                'latitude',
                'longitude',
            ]
        }),
        ('Status & Activity', {
            'fields': [
                'status',
                'is_active',
            ]
        }),
        ('Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ('collapse',),
        }),
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Optional: Show pending restaurants first
        return qs.order_by('status', '-created_at')


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ['name', 'restaurant', 'city', 'min_order', 'is_active']
    list_filter = ['is_active', 'city']
    search_fields = ['name', 'restaurant__brand_name', 'full_address']
    raw_id_fields = ['restaurant']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(RestaurantCategory)
class RestaurantCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'id']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']


class BranchOpeningHoursInline(admin.TabularInline):
    model = BranchOpeningHours
    extra = 0
    fields = ['day', 'is_open', 'shifts']
    readonly_fields = ['day']  # Usually days are fixed (Mon-Sun)

    def has_add_permission(self, request, obj):
        # Prevent adding extra days manually if all 7 already exist
        if obj and obj.opening_hours.count() >= 7:
            return False
        return super().has_add_permission(request, obj)


@admin.register(BranchOpeningHours)
class BranchOpeningHoursAdmin(admin.ModelAdmin):
    list_display = ['branch', 'day', 'is_open']
    list_filter = ['is_open', 'day']
    search_fields = ['branch__name', 'branch__restaurant__brand_name']
    raw_id_fields = ['branch']


@admin.register(RestaurantBankDetail)
class RestaurantBankDetailAdmin(admin.ModelAdmin):
    list_display = ['restaurant', 'bank_name', 'account_holder_name']
    search_fields = ['restaurant__brand_name', 'account_holder_name', 'iban']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['restaurant']


class EmployeeInline(admin.TabularInline):
    model = Employee
    extra = 0
    fields = ['user', 'permissions', 'created_by']
    raw_id_fields = ['user', 'created_by']


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['user', 'branch', 'get_permissions_count', 'created_by', 'created_at']
    list_filter = ['branch', 'created_at']
    search_fields = ['user__username', 'user__email', 'branch__name']
    raw_id_fields = ['user', 'branch', 'created_by']
    readonly_fields = ['created_at', 'updated_at']

    def get_permissions_count(self, obj):
        return len(obj.permissions)
    get_permissions_count.short_description = 'Permissions'

    def has_permission(self, request, obj=None):
        # Optional: Restrict who can manage employees
        return request.user.is_superuser
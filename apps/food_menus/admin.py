from django.contrib import admin
from .models import MenuCategory, MenuItem, ModifierGroup, ModifierOption


# --- Inline for ModifierOption inside ModifierGroup ----------------------------

class ModifierOptionInline(admin.TabularInline):
    model = ModifierOption
    extra = 1
    fields = ("name", "price", "option_type", "sort_order")
    ordering = ("sort_order",)


# --- Inline for ModifierGroup inside MenuItem ----------------------------------

class ModifierGroupInline(admin.TabularInline):
    model = ModifierGroup
    extra = 1
    fields = ("name", "type", "min_select", "max_select", "sort_order")
    ordering = ("sort_order",)
    show_change_link = True


# --- Menu Category Admin -------------------------------------------------------

@admin.register(MenuCategory)
class MenuCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "is_active", "sort_order", "created_at")
    list_filter = ("is_active", "branch")
    search_fields = ("name", "branch__name")
    ordering = ("sort_order", "name")
    list_editable = ("is_active", "sort_order")


# --- Menu Item Admin -----------------------------------------------------------

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "branch",
        "category",
        "price",
        "is_available",
        "sort_order",
        "created_at",
    )
    list_filter = ("is_available", "branch", "category")
    search_fields = ("name", "description", "branch__name", "category__name")
    ordering = ("sort_order", "name")
    list_editable = ("is_available", "sort_order", "price")

    inlines = [ModifierGroupInline]

    fieldsets = (
        ("Basic Info", {
            "fields": ("branch", "category", "name", "description", "photo")
        }),
        ("Pricing & Availability", {
            "fields": ("price", "is_available", "sort_order")
        }),
        ("Extra Info", {
            "fields": ("extra_prep_time", "calories", "dietary_info"),
            "classes": ("collapse",),
        }),
    )


# --- Modifier Group Admin ------------------------------------------------------

@admin.register(ModifierGroup)
class ModifierGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "item", "type", "min_select", "max_select", "sort_order")
    list_filter = ("type", "item__branch")
    search_fields = ("name", "item__name")
    ordering = ("sort_order", "name")

    inlines = [ModifierOptionInline]


# --- Modifier Option Admin -----------------------------------------------------

@admin.register(ModifierOption)
class ModifierOptionAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "price", "option_type", "sort_order")
    list_filter = ("option_type", "group__item__branch")
    search_fields = ("name", "group__name")
    ordering = ("sort_order", "name")
    list_editable = ("price", "option_type", "sort_order")
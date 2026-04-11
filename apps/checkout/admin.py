from django.contrib import admin
from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ["menu_item", "quantity", "item_price", "options_price", "selected_options", "created_at"]
    can_delete = False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "branch", "total", "created_at"]
    list_filter = ["branch__restaurant", "created_at"]
    search_fields = ["customer__phone", "customer__full_name", "branch__name"]
    readonly_fields = ["id", "customer", "branch", "created_at", "updated_at"]
    inlines = [CartItemInline]

    def total(self, obj):
        return obj.total
    total.short_description = "Total (SAR)"


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ["id", "cart", "menu_item", "quantity", "item_price", "options_price", "subtotal", "created_at"]
    list_filter = ["cart__branch__restaurant", "created_at"]
    search_fields = ["menu_item__name", "cart__customer__phone"]
    readonly_fields = ["id", "cart", "menu_item", "item_price", "options_price", "selected_options", "created_at", "updated_at"]

    def subtotal(self, obj):
        return obj.subtotal
    subtotal.short_description = "Subtotal (SAR)"
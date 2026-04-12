from django.contrib import admin
from .models import Cart, CartItem, CustomerCar, Order, OrderItem, OrderRating


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ["menu_item", "quantity", "item_price", "options_price", "selected_options"]
    can_delete = False


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display  = ["id", "customer", "branch", "created_at"]
    search_fields = ["customer__phone", "branch__name"]
    inlines       = [CartItemInline]


@admin.register(CustomerCar)
class CustomerCarAdmin(admin.ModelAdmin):
    list_display  = ["id", "customer", "car_model", "plate_number", "car_color"]
    search_fields = ["customer__phone", "plate_number", "car_model"]


class OrderItemInline(admin.TabularInline):
    model          = OrderItem
    extra          = 0
    readonly_fields = ["menu_item", "name", "price", "options_price", "quantity", "selected_options"]
    can_delete     = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display  = ["order_number", "customer", "branch", "status", "payment_method", "payment_status", "total", "created_at"]
    list_filter   = ["status", "payment_method", "payment_status", "created_at"]
    search_fields = ["order_number", "customer__phone", "branch__name"]
    readonly_fields = ["order_number", "qr_token", "created_at", "updated_at"]
    inlines       = [OrderItemInline]


@admin.register(OrderRating)
class OrderRatingAdmin(admin.ModelAdmin):
    list_display  = ["id", "order", "customer", "stars", "created_at"]
    list_filter   = ["stars"]
    search_fields = ["order__order_number", "customer__phone"]
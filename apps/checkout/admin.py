from django.contrib import admin
from .models import (
    Car,
    Cart,
    CartItem,
    Payment,
    Order,
    OrderItem,
    Feedback,
    CommissionSettings,
    RestaurantCommission,
    OwnerWallet,
    CommissionTransaction,
    PayoutRequest,
    SupportTicket,
)


# ----------------- CAR -----------------

@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "car_model", "plate_number", "color", "created_at")
    search_fields = ("car_model", "plate_number", "customer__email", "customer__username")
    list_filter = ("created_at",)


# ----------------- CART -----------------

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "branch", "created_at")
    search_fields = ("customer__email", "branch__name")
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "menu_item", "quantity", "item_price", "options_price")
    search_fields = ("menu_item__name", "cart__customer__email")
    list_filter = ("created_at",)


# ----------------- PAYMENT -----------------

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "method", "status", "amount", "cash_received_by", "created_at")
    list_filter = ("method", "status", "created_at")
    search_fields = ("stripe_intent_id",)


# ----------------- ORDER -----------------

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "customer",
        "branch",
        "status",
        "total",
        "user_arrived",
        "created_at",
    )
    list_filter = ("status", "created_at", "branch")
    search_fields = ("order_number", "customer__email", "branch__name")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "name", "quantity", "price", "options_price")
    search_fields = ("name", "order__order_number")


# ----------------- FEEDBACK -----------------

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "customer", "stars", "created_at")
    list_filter = ("stars", "created_at")
    search_fields = ("order__order_number", "customer__email")


# ----------------- COMMISSION -----------------

@admin.register(CommissionSettings)
class CommissionSettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "percentage", "percentage_active", "fixed_sar", "fixed_active")


@admin.register(RestaurantCommission)
class RestaurantCommissionAdmin(admin.ModelAdmin):
    list_display = ("id", "restaurant", "percentage", "percentage_active", "fixed_sar")
    search_fields = ("restaurant__brand_name",)


# ----------------- WALLET -----------------

@admin.register(OwnerWallet)
class OwnerWalletAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "balance")
    search_fields = ("owner__email", "owner__username")


# ----------------- TRANSACTIONS -----------------

@admin.register(CommissionTransaction)
class CommissionTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "restaurant", "subtotal", "commission_amount", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("restaurant__brand_name",)


@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "owner",
        "amount",
        "status",
        "bank_name",
        "actioned_by",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("owner__email", "bank_name", "account_number")


# ----------------- SUPPORT -----------------

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "email", "status", "order", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("email", "full_name", "description", "order__order_number")
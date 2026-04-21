from django.contrib import admin
from .models import Car, Cart, CartItem, Payment, Order, OrderItem, Feedback


# -------------------- CAR --------------------
@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "car_model",
        "plate_number",
        "color",
        "created_at",
    )
    search_fields = ("car_model", "plate_number", "customer__email")
    list_filter = ("created_at",)
    autocomplete_fields = ("customer",)


# -------------------- CART ITEM INLINE --------------------
class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ("subtotal",)
    autocomplete_fields = ("menu_item",)


# -------------------- CART --------------------
@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "branch", "total", "created_at")
    search_fields = ("customer__email", "branch__name")
    list_filter = ("branch", "created_at")
    inlines = [CartItemInline]
    autocomplete_fields = ("customer", "branch")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("customer", "branch")


# -------------------- CART ITEM --------------------
@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "cart", "menu_item", "quantity", "subtotal")
    search_fields = ("menu_item__name",)
    autocomplete_fields = ("cart", "menu_item")


# -------------------- PAYMENT --------------------
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "method", "status", "amount", "created_at")
    list_filter = ("method", "status")
    search_fields = ("stripe_intent_id",)
    autocomplete_fields = ("cash_received_by",)
    readonly_fields = ("created_at",)


# -------------------- ORDER ITEM INLINE --------------------
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("subtotal",)


# -------------------- FEEDBACK INLINE --------------------
class FeedbackInline(admin.StackedInline):
    model = Feedback
    extra = 0
    readonly_fields = ("stars", "comment", "created_at")
    can_delete = False


# -------------------- ORDER --------------------
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

    list_filter = ("status", "branch", "user_arrived", "created_at")
    search_fields = ("order_number", "customer__email", "branch__name")
    autocomplete_fields = ("customer", "branch", "car", "payment")

    readonly_fields = (
        "order_number",
        "qr_token",
        "subtotal",
        "service_fee",
        "vat",
        "total",
        "created_at",
        "preparing_at",
        "ready_at",
        "delivered_at",
        "cancelled_at",
    )

    inlines = [OrderItemInline, FeedbackInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("customer", "branch", "payment", "car")
        )


# -------------------- ORDER ITEM --------------------
@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "name", "quantity", "subtotal")
    search_fields = ("name",)
    autocomplete_fields = ("order", "menu_item")


# -------------------- FEEDBACK --------------------
@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("order", "customer", "stars", "created_at")
    search_fields = ("order__order_number", "customer__email")
    list_filter = ("stars", "created_at")
    autocomplete_fields = ("order", "customer")

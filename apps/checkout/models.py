import uuid
from django.db import models
from apps.utils.models import TimeStampedModel

# --- Cart Model Section ------------------------------------------------------------------

class Cart(TimeStampedModel):
    """One active cart per customer per branch."""
    customer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="carts",
    )
    branch = models.ForeignKey(
        "restaurants.Branch",
        on_delete=models.CASCADE,
        related_name="carts",
    )

    class Meta:
        db_table = "carts"
        unique_together = [["customer", "branch"]]

    def __str__(self):
        return f"{self.customer} — {self.branch.name}"

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.all())


class CartItem(TimeStampedModel):
    """A single menu item inside a cart."""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(
        "food_menus.MenuItem",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveSmallIntegerField(default=1)
    selected_options = models.JSONField(
        default=list,
        help_text="List of selected ModifierOption IDs"
    )
    item_price = models.DecimalField(max_digits=8, decimal_places=2)
    options_price = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    class Meta:
        db_table = "cart_items"

    def __str__(self):
        return f"{self.menu_item.name} x{self.quantity}"

    @property
    def subtotal(self):
        return (self.item_price + self.options_price) * self.quantity

# --- Customer Car Model for Curbside Pickup --------------------------------------------------

class CustomerCar(TimeStampedModel):
    """Cars saved by a customer for curbside pickup."""
    customer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="cars",
    )
    car_model = models.CharField(max_length=100)
    plate_number = models.CharField(max_length=20)
    car_color = models.CharField(max_length=7, help_text="Hex color e.g. #FF0000")

    class Meta:
        db_table = "customer_cars"

    def __str__(self):
        return f"{self.car_model} — {self.plate_number}"
    
class Order(TimeStampedModel):

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentMethod(models.TextChoices):
        STRIPE = "stripe", "Stripe"
        HAND_CASH  = "hand_cash", "Hand Cash"

    class PaymentStatus(models.TextChoices):
        PENDING  = "pending", "Pending"
        PAID     = "paid", "Paid"
        FAILED   = "failed", "Failed"

    order_number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="orders",
    )
    branch = models.ForeignKey(
        "restaurants.Branch",
        on_delete=models.SET_NULL,
        null=True,
        related_name="orders",
    )
    car = models.ForeignKey(
        CustomerCar,
        on_delete=models.SET_NULL,
        null=True,
        related_name="orders",
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)

    note = models.TextField(blank=True, default="")
    pickup_time = models.CharField(max_length=50, blank=True, default="")

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    service_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vat = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # QR code token for delivery confirmation
    qr_token = models.CharField(max_length=64, unique=True, null=True, blank=True)

    # Timestamps for each status change
    accepted_at = models.DateTimeField(null=True, blank=True)
    preparing_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Employee who handled cash
    cash_confirmed_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="cash_confirmed_orders",
    )

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]

    def __str__(self):
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_order_number():
        import random
        return f"ORD-{random.randint(1000, 9999)}"
    
class OrderItem(TimeStampedModel):
    order     = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(
        "food_menus.MenuItem",
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_items",
    )
    name = models.CharField(max_length=200)   # snapshot
    price = models.DecimalField(max_digits=8, decimal_places=2)
    options_price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    quantity = models.PositiveSmallIntegerField(default=1)
    selected_options = models.JSONField(default=list)    # snapshot [{name, price}]

    class Meta:
        db_table = "order_items"

    @property
    def subtotal(self):
        return (self.price + self.options_price) * self.quantity
    
class OrderRating(TimeStampedModel):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="rating")
    customer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    stars = models.PositiveSmallIntegerField()   # 1-5
    feedback = models.TextField(blank=True, default="")

    class Meta:
        db_table = "order_ratings"

    def __str__(self):
        return f"{self.order.order_number} — {self.stars}★"
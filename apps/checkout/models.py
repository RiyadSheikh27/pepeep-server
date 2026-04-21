import uuid
import secrets
from django.db import models
from apps.utils.models import TimeStampedModel


#  --- CAR ---------------------------------------------------------------------------


class Car(TimeStampedModel):
    """Customer's car saved for curbside pickup."""

    customer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="cars",
    )
    car_model = models.CharField(max_length=100)
    plate_number = models.CharField(max_length=20)
    color = models.CharField(max_length=7, help_text="Hex color e.g. #FF0000")

    class Meta:
        db_table = "cars"

    def __str__(self):
        return f"{self.car_model} — {self.plate_number}"


#  --- CART ---------------------------------------------------------------------------


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
        default=list, help_text="List of selected ModifierOption IDs"
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


#  --- PAYMENT ---------------------------------------------------------------------------


class Payment(TimeStampedModel):

    class Method(models.TextChoices):
        STRIPE = "stripe", "Stripe"
        CASH = "cash", "Cash"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    # stripe_intent_id is set when method=STRIPE at checkout initiation
    stripe_intent_id = models.CharField(
        max_length=200, null=True, blank=True, db_index=True
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # cash only — filled when employee clicks "Receive Cash"
    cash_received_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_received_payments",
    )
    cash_received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments"

    def __str__(self):
        return f"{self.method} — {self.status} — {self.amount}"


#  --- ORDER ---------------------------------------------------------------------------


class Order(TimeStampedModel):

    class Status(models.TextChoices):
        ORDER_SENT = "order_sent", "Order Sent"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

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
        Car,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    payment = models.OneToOneField(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ORDER_SENT, db_index=True
    )
    note = models.TextField(blank=True, default="")
    pickup_time = models.CharField(max_length=50, blank=True, default="")

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    service_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vat = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # QR delivery token — generated on order creation, cleared after scan
    qr_token = models.CharField(max_length=64, unique=True, null=True, blank=True)

    # Arrival flag — set by Celery task when user taps "I Arrived"
    user_arrived = models.BooleanField(default=False)
    user_arrived_at = models.DateTimeField(null=True, blank=True)

    # Customer location snapshot at arrival (optional, for distance/ETA)
    arrived_lat = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    arrived_lon = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    # Status timestamps
    preparing_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

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

        return f"ORD-{random.randint(10000, 99999)}"


#  --- ORDER ITEM  (snapshot at time of order) ---------------------------------------------------------------------------


class OrderItem(TimeStampedModel):

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(
        "food_menus.MenuItem",
        on_delete=models.SET_NULL,
        null=True,
        related_name="order_items",
    )
    # snapshots — survive if menu item is edited later
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    options_price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    quantity = models.PositiveSmallIntegerField(default=1)
    # snapshot: [{"name": "Extra Cheese", "price": "2.00"}, ...]
    selected_options = models.JSONField(default=list)

    class Meta:
        db_table = "order_items"

    @property
    def subtotal(self):
        return (self.price + self.options_price) * self.quantity

    def __str__(self):
        return f"{self.name} x{self.quantity}"


#  --- FEEDBACK ---------------------------------------------------------------------------


class Feedback(TimeStampedModel):
    """Post-delivery rating + comment from customer."""

    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name="feedback"
    )
    customer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="feedbacks",
    )
    stars = models.PositiveSmallIntegerField()  # 1–5
    comment = models.TextField(blank=True, default="")

    class Meta:
        db_table = "order_feedbacks"

    def __str__(self):
        return f"{self.order.order_number} — {self.stars}★"

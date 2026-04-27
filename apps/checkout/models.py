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
        WALLET = "wallet", "Wallet"

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


# --- COMISSION SETTINGS ---------------------------------------------------------------------------


class CommissionSettings(TimeStampedModel):
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    percentage_active = models.BooleanField(default=False)
    fixed_sar = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fixed_active = models.BooleanField(default=False)

    class Meta:
        db_table = "commission_settings"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    def calculate(self, subtotal):
        from decimal import Decimal

        total = Decimal("0")
        if self.percentage_active and self.percentage:
            total += subtotal * (self.percentage / Decimal("100"))
        if self.fixed_active and self.fixed_sar:
            total += self.fixed_sar
        return total.quantize(Decimal("0.01"))

    def __str__(self):
        return f"Commission: {self.percentage}% + {self.fixed_sar} SAR"


class RestaurantCommission(TimeStampedModel):
    restaurant = models.OneToOneField(
        "restaurants.Restaurant", on_delete=models.CASCADE, related_name="commission"
    )
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    percentage_active = models.BooleanField(default=True)
    fixed_sar = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    fixed_active = models.BooleanField(default=False)

    class Meta:
        db_table = "restaurant_commissions"

    def calculate(self, subtotal):
        from decimal import Decimal

        total = Decimal("0")
        if self.percentage_active and self.percentage:
            total += subtotal * (self.percentage / Decimal("100"))
        if self.fixed_active and self.fixed_sar:
            total += self.fixed_sar
        return total.quantize(Decimal("0.01"))

    def __str__(self):
        return f"{self.restaurant.brand_name}: {self.percentage}%"


# --- OWNER WALLET SETTINGS ---------------------------------------------------------------------------
class OwnerWallet(TimeStampedModel):
    owner = models.OneToOneField(
        "authentication.User", on_delete=models.CASCADE, related_name="wallet"
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = "owner_wallets"

    def __str__(self):
        return f"{self.owner} — {self.balance} SAR"


# --- COMMISSION AND PAYOUT TRANSACTIONS ---------------------------------------------------------------------------


class CommissionTransaction(TimeStampedModel):

    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        PENDING = "pending", "Pending"

    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        on_delete=models.SET_NULL,
        null=True,
        related_name="commission_transactions",
    )
    order = models.OneToOneField(
        "checkout.Order",
        on_delete=models.SET_NULL,
        null=True,
        related_name="commission_transaction",
    )
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.COMPLETED
    )

    class Meta:
        db_table = "commission_transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"TXN | {self.restaurant} | {self.commission_amount} SAR"


class PayoutRequest(TimeStampedModel):

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"

    owner = models.ForeignKey(
        "authentication.User", on_delete=models.CASCADE, related_name="payout_requests"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    bank_name = models.CharField(max_length=100)
    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=50)
    note = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )
    rejection_reason = models.TextField(blank=True, default="")
    actioned_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actioned_payouts",
    )
    actioned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payout_requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"PO | {self.owner} | {self.amount} SAR | {self.status}"


# --- SUPPORT TICKETS ---------------------------------------------------------------------------


class SupportTicket(TimeStampedModel):

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    customer = models.ForeignKey(
        "authentication.User", on_delete=models.CASCADE, related_name="support_tickets"
    )
    order = models.ForeignKey(
        "checkout.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
    )
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    description = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN
    )
    admin_reply = models.TextField(blank=True, default="")
    replied_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_replies",
    )
    is_viewed = models.BooleanField(default=False)
    viewed_at = models.DateTimeField(null=True, blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "support_tickets"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Ticket-{self.id} | {self.customer} | {self.status}"


#  --- CUSTOMER WALLET ---------------------------------------------------------------------------


class CustomerWallet(TimeStampedModel):
    """One wallet per customer. Used for wallet-pay orders."""

    customer = models.OneToOneField(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="customer_wallet",
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = "customer_wallets"

    def __str__(self):
        return f"{self.customer} — {self.balance} SAR"


class CustomerWalletTransaction(TimeStampedModel):
    """Audit log for every wallet balance change."""

    class TxType(models.TextChoices):
        CREDIT = "credit", "Credit"
        DEBIT = "debit", "Debit"
        BONUS = "bonus", "Bonus"
        ORDER_PAY = "order_pay", "Order Payment"
        REFUND = "refund", "Refund"

    wallet = models.ForeignKey(
        CustomerWallet, on_delete=models.CASCADE, related_name="transactions"
    )
    tx_type = models.CharField(max_length=10, choices=TxType.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField(blank=True, default="")
    actioned_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_adjustments",
    )

    class Meta:
        db_table = "customer_wallet_transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tx_type} {self.amount} — {self.wallet.customer}"


#  --- VISIBILITY SETTINGS  (global singleton) ---------------------------------------------------------------------------


class VisibilitySettings(TimeStampedModel):
    """Global platform settings. Only one row (id=1)."""

    radius_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=10,
        help_text="Search radius in km for branch discovery",
    )

    class Meta:
        db_table = "visibility_settings"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(id=1, defaults={"radius_km": 10})
        return obj

    def __str__(self):
        return f"Visibility radius: {self.radius_km} km"


#  --- ADMIN MANAGER ---------------------------------------------------------------------------


class AdminManager(TimeStampedModel):
    """Managers created by super admin. Linked to a User with role=admin."""

    class AccessLevel(models.TextChoices):
        LIMITED = "limited", "Limited Access"
        FULL = "full", "Full Access"

    user = models.OneToOneField(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="manager_profile",
    )
    access_level = models.CharField(
        max_length=10, choices=AccessLevel.choices, default=AccessLevel.LIMITED
    )
    created_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_managers",
    )

    class Meta:
        db_table = "admin_managers"

    def __str__(self):
        return f"{self.user.full_name} ({self.access_level})"

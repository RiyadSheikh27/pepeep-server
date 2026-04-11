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
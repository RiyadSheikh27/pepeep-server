from django.db import models
from apps.utils.models import TimeStampedModel
from apps.restaurants.models import Branch

# --- Menu Section --------------------------------------------------------------------------------

class MenuCategory(TimeStampedModel):
    """ Add Menu Category """
    branch = models.ForeignKey("restaurants.Branch", on_delete=models.CASCADE, related_name="menu_categories",)
    name= models.CharField(max_length=100)
    is_active  = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)
 
    class Meta:
        db_table= "menu_categories"
        ordering= ["sort_order", "name"]
        unique_together = [["branch", "name"]]
 
    def __str__(self):
        return f"{self.branch.name} › {self.name}"
    
class MenuItem(TimeStampedModel):
    """ Add Menu Items """
    DIETARY_CHOICES = [
        ("vegetarian",  "Vegetarian"),
        ("vegan",       "Vegan"),
        ("gluten_free", "Gluten Free"),
        ("dairy_free",  "Dairy Free"),
        ("nut_free",    "Nut Free"),
        ("halal",       "Halal"),
    ]
    
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="menu_items")
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=200)
    photo = models.FileField(upload_to="menu/items/%Y/%m", null=True, blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    description = models.TextField(blank=True, default="")

    extra_prep_time = models.PositiveSmallIntegerField(default=0, help_text="Extra Minutes")
    calories = models.PositiveSmallIntegerField(null=True, blank=True)

    dietary_info = models.JSONField(default=list, blank=True)

    is_available = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)

    class Meta:
        db_table = "menu_items"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.branch.name})"
    
class ModifierGroup(TimeStampedModel):
    """ Create groups and items under groups of any manu """

    class Type(models.TextChoices):
        OPTIONAL = "optional", "Optional"
        REQUIRED = "required", "Required"

    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="modifier_groups")
    name = models.CharField(max_length=100)
    type       = models.CharField(max_length=10, choices=Type.choices, default=Type.OPTIONAL)
 
    # how many options the customer can select inside this group
    min_select = models.PositiveSmallIntegerField(default=0)
    max_select = models.PositiveSmallIntegerField(default=5)

    sort_order = models.PositiveSmallIntegerField(default=0)
 
    class Meta:
        db_table = "menu_modifier_groups"
        ordering = ["sort_order", "name"]
 
    def __str__(self):
        return f"{self.item.name} › {self.name}"
    
class ModifierOption(TimeStampedModel):
    """ A single option inside a Modifier Group """
    class OptionType(models.TextChoices):
        ADDITION = "addition", "Addition"
        FREE = "free", "Free"

    group= models.ForeignKey(ModifierGroup, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    option_type = models.CharField(max_length=10, choices=OptionType.choices, default=OptionType.FREE)
    sort_order = models.PositiveSmallIntegerField(default=0)
 
    class Meta:
        db_table = "menu_modifier_options"
        ordering = ["sort_order", "name"]
 
    def __str__(self):
        return f"{self.group.name} - {self.name}"
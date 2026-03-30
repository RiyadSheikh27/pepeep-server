from django.db import models
from apps.utils.models import TimeStampedModel


class Restaurant(TimeStampedModel):

    class Category(models.TextChoices):
        FAST_FOOD   = "fast_food",   "Fast Food"
        CASUAL      = "casual",      "Casual Dining"
        FINE_DINING = "fine_dining", "Fine Dining"
        CAFE        = "cafe",        "Café"
        BAKERY      = "bakery",      "Bakery"
        PIZZA       = "pizza",       "Pizza"
        SUSHI       = "sushi",       "Sushi"
        SHAWARMA    = "shawarma",    "Shawarma"
        SEAFOOD     = "seafood",     "Seafood"
        OTHER       = "other",       "Other"

    class Status(models.TextChoices):
        PENDING  = "pending",  "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    owner = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="restaurants",
    )

    # Step 2
    legal_name        = models.CharField(max_length=200)
    brand_name        = models.CharField(max_length=200)
    name              = models.CharField(max_length=200, blank=True, default="")  # keep for compatibility
    category          = models.CharField(max_length=50, choices=Category.choices, default=Category.OTHER)
    logo              = models.ImageField(upload_to="restaurants/logos/%Y/%m/", null=True, blank=True)
    short_description = models.TextField(blank=True, default="")

    # Step 3 — Legal
    cr_number       = models.CharField(max_length=20, blank=True, default="")
    vat_number      = models.CharField(max_length=20, blank=True, default="")
    cr_document     = models.FileField(upload_to="restaurants/docs/%Y/%m/", null=True, blank=True)
    vat_certificate = models.FileField(upload_to="restaurants/docs/%Y/%m/", null=True, blank=True)

    # Step 3 — Address
    short_address             = models.CharField(max_length=200, blank=True, default="")
    street_name               = models.CharField(max_length=200, blank=True, default="")
    building_number           = models.CharField(max_length=20,  blank=True, default="")
    building_secondary_number = models.CharField(max_length=20,  blank=True, default="")
    district                  = models.CharField(max_length=100, blank=True, default="")
    postal_code               = models.CharField(max_length=10,  blank=True, default="")
    unit_number               = models.CharField(max_length=20,  blank=True, default="")
    city                      = models.CharField(max_length=100, blank=True, default="")
    country                   = models.CharField(max_length=100, blank=True, default="Saudi Arabia")

    status    = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "restaurants"

    def __str__(self):
        return self.brand_name or self.name


class Branch(TimeStampedModel):
    restaurant  = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="branches")
    name        = models.CharField(max_length=200)
    city        = models.CharField(max_length=100, blank=True, default="")
    full_address = models.CharField(max_length=300, blank=True, default="")
    min_order   = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_active   = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "branches"

    def __str__(self):
        return f"{self.restaurant.brand_name} — {self.name}"


class BranchOpeningHours(TimeStampedModel):
    DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    branch  = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="opening_hours")
    day     = models.CharField(max_length=10)
    is_open = models.BooleanField(default=True)
    shifts  = models.JSONField(default=list)  # [{"open": "09:00", "close": "22:00"}, ...]

    class Meta:
        db_table = "branch_opening_hours"
        unique_together = [["branch", "day"]]

    def __str__(self):
        return f"{self.branch.name} — {self.day}"


class RestaurantBankDetail(TimeStampedModel):

    class BankName(models.TextChoices):
        AL_RAJHI = "al_rajhi", "Al Rajhi Bank"
        SNB      = "snb",      "Saudi National Bank"
        RIYAD    = "riyad",    "Riyad Bank"
        SAMBA    = "samba",    "Samba Financial Group"
        ALINMA   = "alinma",   "Alinma Bank"
        BSF      = "bsf",      "Banque Saudi Fransi"
        ARAB     = "arab",     "Arab National Bank"
        SIB      = "sib",      "Saudi Investment Bank"
        OTHER    = "other",    "Other"

    restaurant          = models.OneToOneField(Restaurant, on_delete=models.CASCADE, related_name="bank_detail")
    bank_name           = models.CharField(max_length=50, choices=BankName.choices)
    account_holder_name = models.CharField(max_length=200)
    iban                = models.CharField(max_length=34)
    bank_iban_pdf       = models.FileField(upload_to="restaurants/bank/%Y/%m/")

    class Meta:
        db_table = "restaurant_bank_details"

    def __str__(self):
        return f"{self.restaurant.brand_name} — {self.bank_name}"


class Employee(TimeStampedModel):

    class Permission(models.TextChoices):
        DASHBOARD     = "dashboard",     "View Dashboard"
        EDIT_MENU     = "edit_menu",     "Edit Menu"
        CONFIRM_ORDER = "confirm_order", "Confirm Orders"
        VIEW_REPORTS  = "view_reports",  "View Reports"
        MANAGE_STAFF  = "manage_staff",  "Manage Staff"

    ALL_PERMISSIONS = [p.value for p in Permission]

    user       = models.OneToOneField(
        "authentication.User", on_delete=models.CASCADE, related_name="employee_profile"
    )
    branch     = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="employees")
    permissions = models.JSONField(default=list)
    created_by = models.ForeignKey(
        "authentication.User", on_delete=models.SET_NULL, null=True, related_name="created_employees"
    )

    class Meta:
        db_table = "employees"

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions

    def __str__(self):
        return f"{self.user.username} @ {self.branch}"
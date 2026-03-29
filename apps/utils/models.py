import uuid
from django.db import models
from django.utils import timezone

# --- Base model with UUID PK and timestamps --------------------------------

class TimeStampedModel(models.Model):
    """
    Abstract base for every model in the project.
    Provides UUID primary key + created_at / updated_at audit fields.
    Always use this instead of models.Model directly.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]

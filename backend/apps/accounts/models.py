import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    """Custom user model with a UUID primary key.

    Declared before the first migration per Django's recommendation, since
    swapping AUTH_USER_MODEL after migrations exist requires a data migration.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(blank=False)

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="unique_user_email_lower"),
        ]

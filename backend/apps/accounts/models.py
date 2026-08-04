import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model with a UUID primary key.

    Declared before the first migration per Django's recommendation, since
    swapping AUTH_USER_MODEL after migrations exist requires a data migration.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

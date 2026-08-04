import uuid

from django.db import models


class UUIDPrimaryKeyModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDPrimaryKeyModel, TimeStampedModel):
    class Meta:
        abstract = True


class OrganizationScopedModel(BaseModel):
    """Base for every tenant-owned model.

    Uses a string FK reference so apps.core never imports apps.organizations.
    """

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)

    class Meta:
        abstract = True

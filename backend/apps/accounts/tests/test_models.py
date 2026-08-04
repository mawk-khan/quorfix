import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

User = get_user_model()


@pytest.mark.django_db
def test_email_uniqueness_is_case_insensitive_at_the_db_level(make_user):
    """The DB constraint is defense in depth beyond app-level lowercasing:
    bypass the fixture's normalization to prove the DB itself rejects a
    differently-cased duplicate, not just the application convention.
    """
    make_user("someone@example.com")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(
                username=uuid.uuid4().hex,
                email="Someone@Example.com",
                password="Str0ngPassw0rd!",
            )

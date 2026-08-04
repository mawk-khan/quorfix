from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailAuthBackend(ModelBackend):
    """Authenticates by (case-insensitive) email + password instead of username."""

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        email = email or username
        if email is None or password is None:
            return None
        try:
            user = User.objects.get(email=email.lower())
        except User.DoesNotExist:
            # Run the hasher anyway so login timing doesn't reveal whether the
            # email exists.
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

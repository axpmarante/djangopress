from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.mixins import UserPassesTestMixin


def superuser_required(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME, login_url=None):
    """Decorator that requires the user to be an active superuser."""
    actual_decorator = user_passes_test(
        lambda u: u.is_active and u.is_superuser,
        login_url=login_url,
        redirect_field_name=redirect_field_name,
    )
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator


class SuperuserRequiredMixin(UserPassesTestMixin):
    """Mixin that requires the user to be an active superuser."""

    def test_func(self):
        return self.request.user.is_active and self.request.user.is_superuser

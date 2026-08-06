"""Optional, request-scoped actor context (authenticated user/organization
IDs) for the logging filter in apps.core.logging.

Deliberately its own tiny module with no dependency on
apps.core.middleware.request_id or apps.core.logging: both of those need to
import from here (the middleware to clear it, the filter to read it), and a
shared dependency-free leaf module is what keeps that from becoming a
circular import.

Nothing here ever queries the database — apps.organizations.authentication
calls bind_actor_context() only after it has already resolved the user and
membership through its own normal (single, already-necessary) query, so this
module just stores the resulting IDs for the rest of the request.
"""

from __future__ import annotations

import contextvars

_user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_user_id", default=None
)
_organization_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_organization_id", default=None
)


def bind_actor_context(*, user_id=None, organization_id=None) -> None:
    _user_id_var.set(str(user_id) if user_id else None)
    _organization_id_var.set(str(organization_id) if organization_id else None)


def clear_actor_context() -> None:
    _user_id_var.set(None)
    _organization_id_var.set(None)


def get_user_id() -> str | None:
    return _user_id_var.get()


def get_organization_id() -> str | None:
    return _organization_id_var.get()

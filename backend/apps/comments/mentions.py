"""Mention parsing and resolution.

Mentions are parsed from the comment's raw markdown *source*, never from
rendered HTML — a client-side renderer can always be bypassed, skipped, or
misconfigured, so the only structural guarantee comes from parsing the text
actually persisted to the database. Syntax: ``@[Display Name](mention:<uuid>)``,
inserted by the frontend's mention picker. The display name is purely cosmetic
and is never trusted for identity — only the UUID is ever used to resolve who
was actually mentioned.
"""

import re
import uuid

from apps.organizations.models import OrganizationMembership

# The display-name segment is bounded and newline-free (no unbounded/greedy
# matching across a whole comment body); the id segment is intentionally loose
# (any hex/hyphen run of the right length) because the real validation is the
# strict uuid.UUID(...) parse below, not the regex.
MENTION_TOKEN_RE = re.compile(r"@\[[^\[\]\n]{1,100}\]\(mention:([0-9a-fA-F-]{36})\)")


def extract_mention_user_ids(body: str) -> list[uuid.UUID]:
    """Every syntactically valid mention token in `body`, deduplicated in
    first-seen order. A token whose id segment isn't a real UUID is silently
    skipped rather than raised — an invalid mention token is just inert text,
    never a request error."""
    seen: dict[uuid.UUID, None] = {}
    for raw_id in MENTION_TOKEN_RE.findall(body):
        try:
            parsed = uuid.UUID(raw_id)
        except ValueError:
            continue
        seen.setdefault(parsed, None)
    return list(seen)


def resolve_mentions(organization, user_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Narrows `user_ids` down to those that are actually members of
    `organization` right now. This — not the frontend's suggestion dropdown — is
    what structurally prevents cross-organization mentions: a foreign or
    non-member id is dropped silently, with no distinction surfaced anywhere
    between "not a member" and "no such user", so a comment body can never be
    used to probe another organization's membership."""
    if not user_ids:
        return []
    valid_ids = set(
        OrganizationMembership.objects.filter(
            organization=organization, user_id__in=user_ids
        ).values_list("user_id", flat=True)
    )
    return [uid for uid in user_ids if uid in valid_ids]

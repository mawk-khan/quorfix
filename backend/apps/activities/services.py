from apps.activities.models import BugActivity


def record_bug_activity(
    *,
    bug,
    actor,
    verb: str,
    from_value: str = "",
    to_value: str = "",
    metadata: dict | None = None,
) -> BugActivity:
    """The single write path for bug activity rows.

    apps.bugs.services calls this (via a local import — see that module for
    why) instead of creating BugActivity rows directly, so every activity
    entry is shaped consistently and apps.bugs never needs its own copy of
    this logic.
    """
    return BugActivity.objects.create(
        organization=bug.organization,
        bug=bug,
        actor=actor,
        verb=verb,
        from_value=from_value,
        to_value=to_value,
        metadata=metadata or {},
    )


def record_bug_activities_bulk(entries: list[dict]) -> list[BugActivity]:
    """Bulk-safe variant for operations that touch many bugs in one request,
    e.g. clearing every assignment a removed member held across an
    organization. Issues a single INSERT instead of one per affected bug —
    an uncontrolled per-row create() in a Python loop doesn't scale to an
    org with hundreds of bugs assigned to the same person.

    Each entry is a dict with keys: bug, actor, verb, and optionally
    from_value/to_value/metadata.
    """
    objects = [
        BugActivity(
            organization=entry["bug"].organization,
            bug=entry["bug"],
            actor=entry.get("actor"),
            verb=entry["verb"],
            from_value=entry.get("from_value", ""),
            to_value=entry.get("to_value", ""),
            metadata=entry.get("metadata") or {},
        )
        for entry in entries
    ]
    return BugActivity.objects.bulk_create(objects)

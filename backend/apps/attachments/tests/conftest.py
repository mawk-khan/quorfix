import pytest
from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.fixture(autouse=True)
def _attachment_storage_root(tmp_path, settings):
    """Every test in this package writes under a fresh pytest tmp_path, never
    the repository or a path shared across test runs/processes."""
    settings.ATTACHMENTS_LOCAL_ROOT = str(tmp_path / "attachment-storage")


@pytest.fixture
def other_org_bug():
    """A second, fully independent organization/project/bug/user — mirrors
    apps.bugs.tests.test_bug_tenant_isolation's identical fixture, proves
    nothing in apps.attachments ever lets one organization see, mutate, or
    reference another's data."""
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.bugs.models import Bug
    from apps.organizations.models import CommunityRole, Organization, OrganizationMembership
    from apps.projects.models import Project, ProjectStatus

    org = Organization.objects.create(name="Other Co", slug="other-co-attachments")
    project = Project.objects.create(
        organization=org, key="OTH", name="Other", status=ProjectStatus.ACTIVE
    )
    other_user = get_user_model().objects.create_user(
        username="other-org-admin-attachments",
        email="other-org-admin-attachments@example.com",
        password="x",
    )
    OrganizationMembership.objects.create(
        organization=org,
        user=other_user,
        role=CommunityRole.ADMINISTRATOR,
        joined_at=timezone.now(),
    )
    return Bug.objects.create(
        organization=org,
        project=project,
        number=1,
        key="OTH-1",
        title="Other org's bug",
        reporter=other_user,
    )


@pytest.fixture
def other_org_attachment(other_org_bug):
    from apps.attachments.services import initiate_upload
    from apps.organizations.selectors import get_membership_for_user

    reporter = other_org_bug.reporter
    membership = get_membership_for_user(reporter)
    return initiate_upload(
        bug=other_org_bug,
        uploader=reporter,
        membership=membership,
        original_filename="theirs.txt",
        content_type="text/plain",
        size_bytes=11,
    )


@pytest.fixture
def make_attachment(db):
    """Goes through the real apps.attachments.services.initiate_upload — not a
    bare Attachment.objects.create — leaves the row PENDING (no bytes
    written)."""
    from apps.attachments.services import initiate_upload
    from apps.organizations.selectors import get_membership_for_user

    def _make(
        bug,
        uploader,
        membership=None,
        original_filename="notes.txt",
        content_type="text/plain",
        size_bytes=11,
    ):
        if membership is None:
            membership = get_membership_for_user(uploader)
        return initiate_upload(
            bug=bug,
            uploader=uploader,
            membership=membership,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=size_bytes,
        )

    return _make


@pytest.fixture
def make_uploaded_attachment(make_attachment):
    """Goes through the real receive_local_upload with real bytes on disk —
    for content_type="text/plain" (the default) any content without a NUL
    byte passes signature verification trivially."""
    from apps.attachments.services import receive_local_upload

    def _make(
        bug,
        uploader,
        membership=None,
        content=b"hello world",
        content_type="text/plain",
        original_filename="notes.txt",
    ):
        attachment = make_attachment(
            bug,
            uploader,
            membership=membership,
            original_filename=original_filename,
            content_type=content_type,
            size_bytes=len(content),
        )
        uploaded_file = SimpleUploadedFile(original_filename, content, content_type=content_type)
        return receive_local_upload(
            attachment=attachment, actor=uploader, uploaded_file=uploaded_file
        )

    return _make

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.organizations.models import CommunityRole, Organization, OrganizationMembership

User = get_user_model()

DEFAULT_PASSWORD = "Str0ngPassw0rd!"


@pytest.fixture
def password():
    return DEFAULT_PASSWORD


@pytest.fixture
def make_user(db):
    def _make(email, password=DEFAULT_PASSWORD, **kwargs):
        import uuid

        return User.objects.create_user(
            username=uuid.uuid4().hex, email=email.lower(), password=password, **kwargs
        )

    return _make


@pytest.fixture
def organization(db):
    return Organization.objects.create(name="Acme", slug="acme")


@pytest.fixture
def make_membership(db):
    def _make(organization, user, role=CommunityRole.ADMINISTRATOR):
        return OrganizationMembership.objects.create(
            organization=organization, user=user, role=role, joined_at=timezone.now()
        )

    return _make


@pytest.fixture
def admin_user(make_user):
    return make_user("admin@example.com")


@pytest.fixture
def admin_membership(organization, admin_user, make_membership):
    return make_membership(organization, admin_user, role=CommunityRole.ADMINISTRATOR)


@pytest.fixture
def developer_user(make_user):
    return make_user("dev@example.com")


@pytest.fixture
def developer_membership(organization, developer_user, make_membership):
    return make_membership(organization, developer_user, role=CommunityRole.DEVELOPER)


@pytest.fixture
def qa_user(make_user):
    return make_user("qa@example.com")


@pytest.fixture
def qa_membership(organization, qa_user, make_membership):
    return make_membership(organization, qa_user, role=CommunityRole.QA)


@pytest.fixture
def reporter_user(make_user):
    return make_user("reporter@example.com")


@pytest.fixture
def reporter_membership(organization, reporter_user, make_membership):
    return make_membership(organization, reporter_user, role=CommunityRole.REPORTER)


@pytest.fixture
def viewer_user(make_user):
    return make_user("viewer@example.com")


@pytest.fixture
def viewer_membership(organization, viewer_user, make_membership):
    return make_membership(organization, viewer_user, role=CommunityRole.VIEWER)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_client(admin_user, admin_membership):
    """Authenticated via a real session (force_login), not force_authenticate.

    force_authenticate bypasses DRF's authentication classes entirely, which
    means OrganizationAwareSessionAuthentication.authenticate() never runs
    and request.organization/request.membership never get set. force_login
    creates a real session so every request still goes through the normal
    authentication pipeline.

    Deliberately does NOT depend on the shared `api_client` fixture: a test
    that pulls in two role-clients at once (e.g. admin_client and
    reporter_client, to act as two different users in one test) would
    otherwise get the *same* underlying APIClient object for both — the
    second force_login() silently overwrites the session the first one set,
    so both fixture names end up authenticated as whichever role's fixture
    happened to resolve last. Each role client gets its own APIClient
    instance so they stay independent when combined.
    """
    client = APIClient()
    client.force_login(admin_user)
    return client


@pytest.fixture
def developer_client(developer_user, developer_membership):
    client = APIClient()
    client.force_login(developer_user)
    return client


@pytest.fixture
def qa_client(qa_user, qa_membership):
    client = APIClient()
    client.force_login(qa_user)
    return client


@pytest.fixture
def reporter_client(reporter_user, reporter_membership):
    client = APIClient()
    client.force_login(reporter_user)
    return client


@pytest.fixture
def viewer_client(viewer_user, viewer_membership):
    client = APIClient()
    client.force_login(viewer_user)
    return client


@pytest.fixture
def make_project(db):
    from apps.projects.models import Project, ProjectStatus

    def _make(organization, key="ENG", name="Engine", status=ProjectStatus.ACTIVE, lead=None):
        return Project.objects.create(
            organization=organization, key=key, name=name, status=status, lead=lead
        )

    return _make


@pytest.fixture
def project(organization, make_project):
    return make_project(organization)


@pytest.fixture
def make_bug(db):
    """Goes through the real apps.bugs.services.create_bug — not a bare
    Bug.objects.create — so every test bug picks up a real sequential
    number/key and every fixture-created bug exercises the same numbering
    path production traffic does."""
    from apps.bugs.services import create_bug
    from apps.organizations.selectors import get_membership_for_user

    def _make(organization, project, reporter, membership=None, **fields):
        if membership is None:
            membership = get_membership_for_user(reporter)
        fields.setdefault("title", "Something is broken")
        return create_bug(
            organization=organization,
            project=project,
            reporter=reporter,
            membership=membership,
            **fields,
        )

    return _make


@pytest.fixture
def bug(organization, project, admin_user, admin_membership, make_bug):
    return make_bug(organization, project, admin_user, membership=admin_membership)


@pytest.fixture
def make_comment(db):
    """Goes through the real apps.comments.services.create_comment — not a bare
    Comment.objects.create — so every fixture-created comment exercises the
    same validation/activity/mention path production traffic does."""
    from apps.comments.services import create_comment
    from apps.organizations.selectors import get_membership_for_user

    def _make(bug, author, membership=None, body="Looks like a real bug."):
        if membership is None:
            membership = get_membership_for_user(author)
        return create_comment(bug=bug, author=author, membership=membership, body=body)

    return _make


@pytest.fixture
def comment(bug, admin_user, admin_membership, make_comment):
    return make_comment(bug, admin_user, membership=admin_membership)

"""/api/schema/ and /api/docs/ (drf-spectacular) must require sign-in, not
drf-spectacular's own AllowAny default — otherwise an anonymous internet
visitor could freely browse the complete API surface. See
SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] in config/settings/base.py.
"""

import pytest
from django.test import Client


@pytest.mark.django_db
class TestApiDocsRequireAuthentication:
    def test_schema_rejects_anonymous_requests(self):
        response = Client().get("/api/schema/")
        assert response.status_code in (401, 403)

    def test_docs_rejects_anonymous_requests(self):
        response = Client().get("/api/docs/")
        assert response.status_code in (401, 403)

    def test_schema_allows_an_authenticated_member(self, developer_client):
        response = developer_client.get("/api/schema/")
        assert response.status_code == 200

    def test_docs_allows_an_authenticated_member(self, developer_client):
        response = developer_client.get("/api/docs/")
        assert response.status_code == 200

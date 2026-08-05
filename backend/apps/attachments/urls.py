from django.urls import path

from apps.attachments.views import (
    AttachmentDetailView,
    AttachmentDownloadView,
    AttachmentListCreateView,
    AttachmentUploadBytesView,
)

urlpatterns = [
    path(
        "bugs/<uuid:bug_id>/attachments/",
        AttachmentListCreateView.as_view(),
        name="attachment-list-create",
    ),
    path(
        "bugs/<uuid:bug_id>/attachments/<uuid:attachment_id>/",
        AttachmentDetailView.as_view(),
        name="attachment-detail",
    ),
    path(
        "bugs/<uuid:bug_id>/attachments/<uuid:attachment_id>/download/",
        AttachmentDownloadView.as_view(),
        name="attachment-download",
    ),
    path(
        "attachments/<uuid:attachment_id>/upload-bytes/",
        AttachmentUploadBytesView.as_view(),
        name="attachment-upload-bytes",
    ),
]

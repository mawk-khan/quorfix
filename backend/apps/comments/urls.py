from django.urls import path

from apps.comments.views import CommentDetailView, CommentListCreateView, CommentRedactView

urlpatterns = [
    path(
        "bugs/<uuid:bug_id>/comments/",
        CommentListCreateView.as_view(),
        name="comment-list-create",
    ),
    path(
        "bugs/<uuid:bug_id>/comments/<uuid:comment_id>/",
        CommentDetailView.as_view(),
        name="comment-detail",
    ),
    path(
        "bugs/<uuid:bug_id>/comments/<uuid:comment_id>/redact/",
        CommentRedactView.as_view(),
        name="comment-redact",
    ),
]

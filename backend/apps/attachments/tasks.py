import logging

from celery import shared_task

from apps.attachments.providers import get_storage_provider, hash_storage_key
from apps.core.task_correlation import task_correlation_context

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def delete_attachment_object(self, storage_key: str) -> None:
    """Dispatched via transaction.on_commit from
    apps.attachments.services.remove_attachment, after the DB row is already
    soft-removed. Idempotent — deleting an already-absent key is not an
    error, so a retried or re-dispatched call is always safe."""
    with task_correlation_context(self):
        key_ref = hash_storage_key(storage_key)
        try:
            get_storage_provider().delete(storage_key)
        except Exception as exc:
            logger.warning(
                "Attachment object cleanup failed for %s (attempt %s/%s)",
                key_ref,
                self.request.retries + 1,
                self.max_retries,
                exc_info=exc,
            )
            try:
                self.retry(
                    exc=exc
                )  # always raises: Retry, or MaxRetriesExceededError once exhausted
            except self.MaxRetriesExceededError:
                logger.error(
                    "Attachment object cleanup permanently failed for %s after %s attempts — "
                    "the DB row is already removed and invisible to every read path; this only "
                    "leaves an orphaned storage object.",
                    key_ref,
                    self.max_retries,
                )

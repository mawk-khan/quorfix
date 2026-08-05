import logging

from celery import shared_task

from apps.attachments.providers import get_storage_provider

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def delete_attachment_object(self, storage_key: str) -> None:
    """Dispatched via transaction.on_commit from
    apps.attachments.services.remove_attachment, after the DB row is already
    soft-removed. Idempotent — deleting an already-absent key is not an
    error, so a retried or re-dispatched call is always safe."""
    try:
        get_storage_provider().delete(storage_key)
    except Exception as exc:
        logger.warning(
            "Attachment object cleanup failed for %s (attempt %s/%s): %s",
            storage_key,
            self.request.retries + 1,
            self.max_retries,
            exc,
        )
        try:
            self.retry(exc=exc)  # always raises: Retry, or MaxRetriesExceededError once exhausted
        except self.MaxRetriesExceededError:
            logger.error(
                "Attachment object cleanup permanently failed for %s after %s attempts — "
                "the DB row is already removed and invisible to every read path; this only "
                "leaves an orphaned storage object.",
                storage_key,
                self.max_retries,
            )

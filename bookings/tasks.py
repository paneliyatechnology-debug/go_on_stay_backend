import logging
from config.celery import app

logger = logging.getLogger(__name__)

if app:
    @app.task(bind=True, max_retries=3, default_retry_delay=60)
    def send_booking_confirmation_email_task(self, booking_id, force_retry=False):
        """
        Asynchronous Celery task for generating and dispatching booking confirmation emails with PDF.
        - Enforces idempotency: does not re-send if already marked sent.
        - Exponential backoff on transient network or SMTP failure (60s, 120s, 240s).
        - If all retries fail, logs error without corrupting booking state.
        """
        from bookings.models import Booking
        from services.booking_email_service import send_booking_confirmation_email

        try:
            booking = Booking.objects.select_related('customer', 'hotel', 'room').get(id=booking_id)
        except Booking.DoesNotExist:
            logger.error(f"[CeleryTask] Booking {booking_id} does not exist. Aborting email task.")
            return {"success": False, "error": "Booking not found"}

        # Task Idempotency Check
        if booking.confirmation_email_sent and not force_retry:
            logger.info(f"[CeleryTask] Booking {booking.booking_id} already sent confirmation email. Skipping duplicate.")
            return {"success": True, "status": "already_sent"}

        try:
            result = send_booking_confirmation_email(booking, force_retry=force_retry)
            if not result.get("success") and result.get("status") == "failed":
                # Retry with exponential backoff
                retry_countdown = 60 * (2 ** self.request.retries)
                logger.warning(f"[CeleryTask] Retrying email delivery for booking {booking.booking_id} in {retry_countdown}s (Attempt {self.request.retries + 1}/3)...")
                raise self.retry(exc=Exception(result.get("error")), countdown=retry_countdown)
            return result
        except Exception as exc:
            logger.error(f"[CeleryTask] Error executing email dispatch task for booking {booking_id}: {exc}")
            retry_countdown = 60 * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=retry_countdown)
else:
    def send_booking_confirmation_email_task(booking_id, force_retry=False):
        """Synchronous fallback when Celery is not running."""
        from bookings.models import Booking
        from services.booking_email_service import send_booking_confirmation_email
        try:
            booking = Booking.objects.get(id=booking_id)
            return send_booking_confirmation_email(booking, force_retry=force_retry)
        except Exception as e:
            logger.error(f"Fallback email delivery failed: {e}")
            return {"success": False, "error": str(e)}

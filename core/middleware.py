import uuid
import threading
import logging

_thread_locals = threading.local()

def get_current_request_id():
    """
    Returns the correlation ID of the request currently being processed by this thread.
    """
    return getattr(_thread_locals, 'request_id', None)


class RequestCorrelationMiddleware:
    """
    Middleware that ensures every incoming request has a unique correlation ID (X-Request-ID).
    If supplied by upstream load balancer / reverse proxy, it is preserved; otherwise a new UUID4 is assigned.
    The ID is attached to the request, set in thread-local context for loggers, and added to the HTTP response header.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Read header from incoming request or generate a new one
        request_id = (
            request.headers.get('X-Request-ID') or
            request.META.get('HTTP_X_REQUEST_ID') or
            uuid.uuid4().hex
        )
        # Sanitize length and character set
        request_id = str(request_id).strip()[:64]
        request.id = request_id
        _thread_locals.request_id = request_id

        response = self.get_response(request)

        # Set correlation ID on the outgoing response
        response['X-Request-ID'] = request_id
        return response

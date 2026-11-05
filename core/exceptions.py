from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.exceptions import (
    ValidationError, AuthenticationFailed, NotAuthenticated,
    PermissionDenied, NotFound, MethodNotAllowed, Throttled, APIException
)
from django.http import Http404
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Standardized API Error Response Handler (TASK-18 / RFC 7807 compliant).
    Guarantees all 4xx/5xx responses adhere to:
    {
      "success": false,
      "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid input provided.",
        "details": {
          "field_name": ["Specific error description."]
        }
      }
    }
    Also maintains backwards-compatible dictionary access for 'detail' and field keys.
    """
    response = drf_exception_handler(exc, context)

    if response is None:
        # Handle unexpected unhandled exceptions (500)
        logger.exception(f"Unhandled server error: {exc}", exc_info=exc)
        return Response({
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred. Please try again later.",
                "details": {}
            },
            "detail": "An unexpected server error occurred. Please try again later."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Determine standard error code and human message
    if isinstance(exc, ValidationError):
        code = "VALIDATION_ERROR"
        message = "Invalid input provided."
    elif isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        code = "AUTHENTICATION_FAILED"
        message = "Authentication credentials were not provided or are invalid."
    elif isinstance(exc, (PermissionDenied, DjangoPermissionDenied)):
        code = "PERMISSION_DENIED"
        message = "You do not have permission to perform this action."
    elif isinstance(exc, (NotFound, Http404)):
        code = "NOT_FOUND"
        message = "The requested resource was not found."
    elif isinstance(exc, MethodNotAllowed):
        code = "METHOD_NOT_ALLOWED"
        message = f"Method '{getattr(context.get('request'), 'method', 'REQUEST')}' not allowed."
    elif isinstance(exc, Throttled):
        code = "THROTTLED"
        wait = getattr(exc, 'wait', None)
        message = f"Request was throttled. Expected available in {wait} seconds." if wait else "Request was throttled."
    else:
        raw_code = getattr(exc, 'default_code', 'API_ERROR')
        code = str(raw_code).upper()
        message = str(getattr(exc, 'detail', exc))

    raw_data = response.data
    details = {}

    if isinstance(raw_data, dict):
        if 'detail' in raw_data and len(raw_data) == 1:
            message = str(raw_data['detail'])
            details = {"detail": raw_data['detail']}
        elif 'error' in raw_data and len(raw_data) == 1 and isinstance(raw_data['error'], str):
            message = raw_data['error']
            details = {"error": raw_data['error']}
        else:
            details = dict(raw_data)
            if 'detail' in raw_data and isinstance(raw_data['detail'], str):
                message = raw_data['detail']
            elif 'non_field_errors' in raw_data and isinstance(raw_data['non_field_errors'], list) and raw_data['non_field_errors']:
                message = str(raw_data['non_field_errors'][0])
    elif isinstance(raw_data, list):
        details = {"errors": raw_data}
        if raw_data:
            message = str(raw_data[0])
    else:
        details = {"error": str(raw_data)}

    # Construct standardized RFC 7807 error payload
    standardized = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details
        },
        # Backwards compatibility fields
        "detail": message
    }

    # Merge flat keys so legacy tests and frontend checking response.data['field'] continue working
    if isinstance(details, dict):
        for k, v in details.items():
            if k not in standardized:
                standardized[k] = v

    response.data = standardized
    return response

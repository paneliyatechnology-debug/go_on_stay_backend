import time
import logging
from django.db import connection
from django.core.cache import cache
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status

logger = logging.getLogger('core.views')

class HealthCheckView(APIView):
    """
    Application Health Check Probe (RFC compliant).
    Used by Kubernetes, AWS ALB, Docker, and uptime monitoring services.
    Verifies database and cache connectivity without exposing internal credentials.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def get(self, request):
        health_status = {
            "status": "healthy",
            "service": "goonstay-backend",
            "timestamp": timezone.now().isoformat(),
            "checks": {
                "database": "unknown",
                "cache": "unknown"
            }
        }
        status_code = status.HTTP_200_OK

        # 1. Database Connectivity Check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                row = cursor.fetchone()
                if row and row[0] == 1:
                    health_status["checks"]["database"] = "connected"
                else:
                    health_status["checks"]["database"] = "degraded"
                    health_status["status"] = "degraded"
                    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        except Exception as e:
            logger.error(f"Health check database error: {e}")
            health_status["checks"]["database"] = "disconnected"
            health_status["status"] = "unhealthy"
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        # 2. Cache Connectivity Check
        try:
            cache_key = "_health_ping"
            cache.set(cache_key, "pong", timeout=10)
            val = cache.get(cache_key)
            if val == "pong":
                health_status["checks"]["cache"] = "connected"
            else:
                health_status["checks"]["cache"] = "degraded"
        except Exception as e:
            logger.warning(f"Health check cache error: {e}")
            health_status["checks"]["cache"] = "disconnected"

        return Response(health_status, status=status_code)


class ReadinessCheckView(APIView):
    """
    Application Readiness Probe.
    Determines if the backend instance is fully ready to accept live user traffic.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM django_migrations;")
            return Response({
                "ready": True,
                "status": "ready_for_traffic",
                "timestamp": timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return Response({
                "ready": False,
                "status": "not_ready",
                "error": "Database not accessible or migrations pending"
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


from django.http import JsonResponse


def bad_request_400(request, exception=None):
    return JsonResponse({
        "success": False,
        "error": {
            "code": "BAD_REQUEST",
            "message": "The request could not be processed due to invalid syntax or parameters."
        },
        "detail": "Invalid request."
    }, status=400)


def permission_denied_403(request, exception=None):
    return JsonResponse({
        "success": False,
        "error": {
            "code": "PERMISSION_DENIED",
            "message": "You do not have permission to access the requested resource."
        },
        "detail": "Permission denied."
    }, status=403)


def not_found_404(request, exception=None):
    return JsonResponse({
        "success": False,
        "error": {
            "code": "NOT_FOUND",
            "message": "The requested endpoint or resource was not found."
        },
        "detail": "Resource not found."
    }, status=404)


def server_error_500(request):
    return JsonResponse({
        "success": False,
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred. Please try again later."
        },
        "detail": "Internal server error."
    }, status=500)


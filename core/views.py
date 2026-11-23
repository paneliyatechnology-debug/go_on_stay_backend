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

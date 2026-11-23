"""
Gunicorn Configuration for GoOnStay Staging & Production Deployment.
Optimized for concurrent async I/O and Django WSGI throughput.
"""
import multiprocessing
import os

# Server Socket
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
backlog = 2048

# Worker Processes
# Standard formula: 2 * CPUs + 1 for CPU-bound, higher for async I/O
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "sync"
worker_connections = 1000
timeout = 60
keepalive = 5

# Process Naming
proc_name = "goonstay_backend"

# Logging
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" [req_id=%({x-request-id}i)s]'

# Worker Lifecycle
max_requests = 1000
max_requests_jitter = 50
preload_app = False

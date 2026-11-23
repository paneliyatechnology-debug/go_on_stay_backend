# ==============================================================================
# DOCKERFILE FOR GOONSTAY BACKEND (STAGING & PRODUCTION)
# Python 3.12 / 3.14 on Debian Bookworm Slim
# ==============================================================================

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Install system dependencies for PostgreSQL, Pillow, ReportLab, and compiling wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install gunicorn psycopg2-binary redis celery

# Copy application source
COPY . /app/

# Create logs directory
RUN mkdir -p /app/logs /app/staticfiles /app/media

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "-c", "gunicorn_config.py"]

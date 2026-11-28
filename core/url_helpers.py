import os
import re
from django.conf import settings

PRIVATE_ORIGIN_REGEX = re.compile(
    r'^https?://(?:localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+|0\.0\.0\.0)(?::\d+)?',
    re.IGNORECASE
)


def to_browser_safe_url(url_or_path, request=None):
    """
    Sanitizes URLs and paths sent to the browser:
    - Strips private IPs (192.168.x.x, 10.x.x.x, 127.0.0.1, localhost), backend ports (:8000).
    - Returns same-origin relative paths (e.g. /api/resource/123/ or /media/hotels/images/pic.jpg).
    - If PUBLIC_APPLICATION_DOMAIN is configured (e.g. https://api.goonstay.com), applies it.
    - Preserves approved external public URLs (Cloudinary, Unsplash).
    """
    if not url_or_path:
        return None
    url_str = str(url_or_path).strip()

    # Strip any internal private IP, localhost, or port
    if PRIVATE_ORIGIN_REGEX.match(url_str):
        url_str = PRIVATE_ORIGIN_REGEX.sub('', url_str)
        if not url_str.startswith('/'):
            url_str = '/' + url_str

    # If it is a relative path and an explicit public application domain is configured, prefix with it
    public_domain = getattr(settings, 'PUBLIC_APPLICATION_DOMAIN', None) or os.getenv('PUBLIC_APPLICATION_DOMAIN', '')
    if public_domain and url_str.startswith('/'):
        clean_domain = str(public_domain).rstrip('/')
        return f"{clean_domain}{url_str}"

    return url_str

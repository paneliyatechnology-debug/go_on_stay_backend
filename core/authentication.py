"""
Enhanced JWT Authentication for GoOnStay.
Provides graceful handling of:
1. Missing / empty token headers (e.g. 'Bearer ' sent from Postman when {{admin_token}} is empty).
2. Unresolved Postman template variables (e.g. 'Bearer {{token}}', 'Bearer null', 'Bearer undefined').
3. Raw JWT tokens passed without the 'Bearer ' prefix (3-segment base64 dot-delimited strings).
Prevents the cryptic 'Authorization header must contain two space-delimited values' exception.
"""

from typing import Optional
from rest_framework_simplejwt.authentication import (
    JWTAuthentication,
    AUTH_HEADER_TYPE_BYTES,
)
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from django.utils.translation import gettext_lazy as _


DUMMY_TOKEN_VALUES = {
    'null',
    'undefined',
    'none',
    '""',
    "''",
    '{{token}}',
    '{{admin_token}}',
    '{{admintoken}}',
    '{{staff_token}}',
    '{{stafftoken}}',
    '{{guest_token}}',
    '{{host_token}}',
    '{{access_token}}',
    '{{access}}',
}


class FlexibleJWTAuthentication(JWTAuthentication):
    """
    Drop-in replacement for rest_framework_simplejwt.authentication.JWTAuthentication.
    Handles malformed or placeholder authorization headers cleanly without throwing
    500 or confusing 'bad_authorization_header' errors when tokens are empty.
    """

    def get_raw_token(self, header: bytes) -> Optional[bytes]:
        """
        Extracts an unvalidated JSON web token from the given 'Authorization'
        header value, gracefully handling empty variables and raw tokens.
        """
        parts = header.split()

        if len(parts) == 0:
            # Empty header
            return None

        # Case 1: Exactly 1 part provided
        if len(parts) == 1:
            first = parts[0]
            # e.g., 'Bearer' or 'JWT' with no token attached (Postman empty variable)
            if first in AUTH_HEADER_TYPE_BYTES:
                # Token value was empty/omitted. Treat as unauthenticated (return None)
                # so DRF permissions handle it cleanly with standard 401 Not Authenticated.
                return None

            # User sent raw JWT directly without 'Bearer ' prefix (header: eyJhbGciOi...)
            if first.count(b'.') == 2:
                return first

            # Unrecognized single value
            return None

        # Case 2: Standard two parts (or more)
        if parts[0] in AUTH_HEADER_TYPE_BYTES:
            token = parts[1]
            token_str = token.decode('utf-8', errors='ignore').strip()

            # Check if value is a placeholder or null/undefined
            if token_str.lower() in DUMMY_TOKEN_VALUES:
                return None

            # Check for any unresolved Postman variable: {{...}}
            if token_str.startswith('{{') and token_str.endswith('}}'):
                return None

            return token

        # If it doesn't match the configured auth header type, let other authenticators handle it
        return None

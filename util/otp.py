import secrets
import hashlib


def generate_otp():
    """
    Generates a cryptographically secure 6-digit random numeric OTP string (100000 - 999999).
    Uses secrets.randbelow() for CSPRNG entropy.
    """
    return str(secrets.randbelow(900000) + 100000)


def hash_otp(otp):
    """Hashes the OTP string using SHA-256 for secure DB comparison."""
    return hashlib.sha256(str(otp).encode('utf-8')).hexdigest()


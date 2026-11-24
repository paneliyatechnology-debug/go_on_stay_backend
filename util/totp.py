"""
RFC 6238 compliant Time-based One-Time Password (TOTP) utility.
Zero external dependencies, standard library only (hmac, hashlib, base64, struct, time, secrets).
Designed for GoOnStay Level 2, Level 3, and Level 4 Manager Multi-Factor Authentication.
"""

import hmac
import hashlib
import base64
import struct
import time
import secrets
from urllib.parse import quote


def generate_totp_secret(length=32):
    """
    Generate a cryptographically secure random base32 encoded secret.
    Default 32 base32 characters (160-bit key as per RFC 4226/6238 recommendations).
    """
    # 20 bytes = 160 bits -> 32 base32 characters without padding
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode('utf-8').rstrip('=')


def _clean_secret(secret):
    """
    Normalize base32 secret and re-pad if necessary.
    """
    clean = str(secret).replace(' ', '').upper()
    pad_len = (8 - (len(clean) % 8)) % 8
    clean += '=' * pad_len
    return base64.b32decode(clean, casefold=True)


def generate_totp_code(secret, time_step=30, digits=6, t=None):
    """
    Generate an RFC 6238 TOTP code for the given secret and timestamp.
    """
    if t is None:
        t = time.time()
    
    counter = int(t // time_step)
    key = _clean_secret(secret)
    counter_bytes = struct.pack('>Q', counter)
    
    mac = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    binary = struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7FFFFFFF
    code = binary % (10 ** digits)
    return f"{code:0{digits}d}"


def verify_totp_code(secret, code, time_step=30, window=1, t=None):
    """
    Verify an RFC 6238 TOTP code against the secret.
    Allows +/- `window` intervals (default 1 = 30 seconds drift tolerance).
    """
    if not secret or not code:
        return False
    
    code_str = str(code).strip()
    if not code_str.isdigit() or len(code_str) != 6:
        return False
    
    if t is None:
        t = time.time()
    
    current_counter = int(t // time_step)
    key = _clean_secret(secret)
    
    for offset in range(-window, window + 1):
        counter = current_counter + offset
        counter_bytes = struct.pack('>Q', counter)
        mac = hmac.new(key, counter_bytes, hashlib.sha1).digest()
        dyn_offset = mac[-1] & 0x0F
        binary = struct.unpack('>I', mac[dyn_offset:dyn_offset + 4])[0] & 0x7FFFFFFF
        computed = binary % 1000000
        computed_code = f"{computed:06d}"
        if hmac.compare_digest(computed_code, code_str):
            return True
            
    return False


def get_provisioning_uri(secret, username, issuer="GoOnStay"):
    """
    Return standard otpauth:// URI for QR code generation in authenticator apps.
    """
    quoted_issuer = quote(issuer)
    label = f"{quoted_issuer}:{quote(username)}"
    return f"otpauth://totp/{label}?secret={secret}&issuer={quoted_issuer}&algorithm=SHA1&digits=6&period=30"


def generate_backup_codes(count=8, length=8):
    """
    Generate a set of alphanumeric backup/recovery codes.
    """
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # omit ambiguous chars (0, O, 1, I)
    codes = []
    for _ in range(count):
        code = ''.join(secrets.choice(chars) for _ in range(length))
        formatted = f"{code[:4]}-{code[4:]}"
        codes.append(formatted)
    return codes


def hash_backup_code(code):
    """
    Hash a single backup code with SHA-256 for secure database storage.
    """
    cleaned = str(code).replace('-', '').strip().upper()
    return hashlib.sha256(cleaned.encode('utf-8')).hexdigest()


def verify_and_consume_backup_code(code, hashed_codes_list):
    """
    Verify if a backup code matches any hashed code in the list.
    If valid, returns (True, remaining_hashed_codes).
    If invalid, returns (False, hashed_codes_list).
    """
    if not code or not hashed_codes_list:
        return False, hashed_codes_list
    
    cleaned_code = str(code).replace('-', '').strip().upper()
    candidate_hash = hashlib.sha256(cleaned_code.encode('utf-8')).hexdigest()
    
    for idx, h in enumerate(hashed_codes_list):
        if hmac.compare_digest(candidate_hash, h):
            # Consume this code by removing it from the list
            remaining = [c for i, c in enumerate(hashed_codes_list) if i != idx]
            return True, remaining
            
    return False, hashed_codes_list

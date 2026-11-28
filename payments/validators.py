import os
import re
import html
from rest_framework import serializers


def validate_support_attachment(file_obj):
    """
    Validates uploaded attachments for GoOnStay Support Tickets:
    1. Maximum file size: 5 MB (5,242,880 bytes).
    2. Extension whitelist: .jpg, .jpeg, .png, .pdf only.
    3. Magic byte inspection to verify actual file content (not just MIME header).
    4. Rejects Windows PE (MZ), Linux ELF, and script executables.
    """
    if not file_obj:
        return file_obj

    # 1. File size check (Max 5 MB)
    max_size = 5 * 1024 * 1024
    if file_obj.size > max_size:
        raise serializers.ValidationError(
            f"Attachment file size ({file_obj.size / (1024 * 1024):.2f} MB) exceeds maximum allowed size of 5 MB."
        )

    # 2. Extension check
    ext = os.path.splitext(file_obj.name)[1].lower()
    allowed_extensions = ['.jpg', '.jpeg', '.png', '.pdf']
    if ext not in allowed_extensions:
        raise serializers.ValidationError(
            f"File extension '{ext}' is not permitted. Supported formats are: JPG, JPEG, PNG, and PDF."
        )

    # 3. Read leading bytes for magic signature inspection
    pos = file_obj.tell() if hasattr(file_obj, 'tell') else 0
    header = file_obj.read(32)
    if hasattr(file_obj, 'seek'):
        file_obj.seek(pos)

    # Rejection of executable / script signatures
    if header.startswith(b'MZ') or header.startswith(b'\x7fELF') or header.startswith(b'#!') or header.startswith(b'PK\x03\x04\x14\x00\x08'):
        raise serializers.ValidationError("Executable and archive files are strictly prohibited.")

    is_png = header.startswith(b'\x89PNG\r\n\x1a\n')
    is_jpeg = header.startswith(b'\xff\xd8\xff')
    is_pdf = header.startswith(b'%PDF-')

    if ext in ['.jpg', '.jpeg'] and not is_jpeg:
        raise serializers.ValidationError("File content does not match genuine JPEG image format.")
    elif ext == '.png' and not is_png:
        raise serializers.ValidationError("File content does not match genuine PNG image format.")
    elif ext == '.pdf' and not is_pdf:
        raise serializers.ValidationError("File content does not match genuine PDF document format.")

    # Defense-in-depth: Randomize filename with UUID to prevent exposure of client private filenames or paths
    import uuid
    if hasattr(file_obj, 'name'):
        file_obj.name = f"{uuid.uuid4().hex}{ext}"

    return file_obj


def sanitize_text_input(val):
    """
    Sanitizes user-provided text inputs (subject, description, chat messages)
    to protect against Cross-Site Scripting (XSS):
    - Strips <script> and <style> tags and their contents.
    - Neutralizes inline JavaScript event handlers (e.g. onerror=, onload=).
    - Neutralizes javascript: pseudo-protocols.
    - Encodes raw HTML entities so text renders safely without injection.
    """
    if not val or not isinstance(val, str):
        return val

    # Strip entire script and style blocks
    cleaned = re.sub(r'<script.*?>.*?</script>', '', val, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<style.*?>.*?</style>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Remove inline JavaScript triggers
    cleaned = re.sub(r'on\w+\s*=', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'javascript\s*:', '', cleaned, flags=re.IGNORECASE)

    # Escape HTML special characters
    return html.escape(cleaned).strip()

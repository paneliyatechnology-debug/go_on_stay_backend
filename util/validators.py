import re
from datetime import date, datetime
from rest_framework import serializers

# 1. Indian Mobile Number Validator
# Indian numbers are 10 digits starting with 6, 7, 8, or 9.
# Optionally preceded by +91, 91, or 0.
INDIAN_PHONE_REGEX = re.compile(r'^(?:\+91[\-\s]?|91[\-\s]?|0)?[6-9]\d{9}$')

def clean_indian_phone(value):
    """
    Cleans and normalizes an Indian phone number to 10 digits.
    Raises serializers.ValidationError if invalid.
    """
    if not value:
        return ""
    val_str = str(value).strip()
    # Strip spaces, hyphens, brackets
    clean_val = re.sub(r'[\s\-\(\)\.]', '', val_str)
    
    # Remove leading +91, 91, or 0
    if clean_val.startswith('+91'):
        clean_val = clean_val[3:]
    elif clean_val.startswith('91') and len(clean_val) == 12:
        clean_val = clean_val[2:]
    elif clean_val.startswith('0') and len(clean_val) == 11:
        clean_val = clean_val[1:]

    if not re.match(r'^[6-9]\d{9}$', clean_val):
        raise serializers.ValidationError(
            f"Invalid Indian mobile number '{val_str}'. Must be a 10-digit number starting with 6, 7, 8, or 9 (e.g., 9876543210 or +919876543210)."
        )
    return clean_val


# 2. Strict Email Validator
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

def clean_email(value):
    """
    Validates and normalizes an email address.
    """
    if not value:
        raise serializers.ValidationError("Email address is required.")
    email_clean = str(value).strip().lower()
    
    if not EMAIL_REGEX.match(email_clean) or '..' in email_clean:
        raise serializers.ValidationError(f"Invalid email address format: '{value}'. Please enter a valid email address.")
    
    domain_part = email_clean.split('@')[-1]
    if '.' not in domain_part or len(domain_part.split('.')[-1]) < 2:
        raise serializers.ValidationError(f"Invalid domain in email address: '{value}'.")
        
    return email_clean


# 3. Indian Bank Account Number Validator
# Indian bank accounts range from 9 to 18 numeric digits
def validate_indian_bank_account(value):
    if not value:
        return None
    val_clean = re.sub(r'[\s\-]', '', str(value).strip())
    if not re.match(r'^\d{9,18}$', val_clean):
        raise serializers.ValidationError(
            "Invalid Indian Bank Account Number. Must be between 9 and 18 numeric digits without letters or special characters."
        )
    return val_clean


# 4. Indian IFSC Code Validator
# Format: 4 letters (Bank Code), followed by '0', followed by 6 alphanumeric characters
IFSC_REGEX = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')

def validate_indian_ifsc(value):
    if not value:
        return None
    val_clean = str(value).strip().upper()
    if not IFSC_REGEX.match(val_clean):
        raise serializers.ValidationError(
            f"Invalid IFSC code '{value}'. Must be exactly 11 characters starting with 4 alphabets, fifth character as '0', followed by 6 alphanumeric characters (e.g., HDFC0001234, SBIN0001234)."
        )
    return val_clean


# 5. Indian UPI ID (VPA) Validator
# Format: username@handle (e.g. user@okhdfcbank, 9876543210@paytm, merchant@upi)
UPI_REGEX = re.compile(r'^[a-zA-Z0-9.\-_]{2,64}@[a-zA-Z0-9]{2,32}$')

def validate_indian_upi(value):
    if not value:
        return None
    val_clean = str(value).strip().lower()
    if not UPI_REGEX.match(val_clean):
        raise serializers.ValidationError(
            f"Invalid UPI ID / VPA '{value}'. Must follow standard format like username@bankhandle (e.g., rahul@okhdfcbank, 9876543210@ybl, host@upi)."
        )
    return val_clean


# 6. Indian Postal PIN Code Validator
# 6 digits, first digit cannot be 0
PINCODE_REGEX = re.compile(r'^[1-9][0-9]{5}$')

def validate_indian_pincode(value):
    if not value:
        return None
    val_clean = str(value).strip()
    if not PINCODE_REGEX.match(val_clean):
        raise serializers.ValidationError(
            f"Invalid Indian PIN Code '{value}'. Must be a 6-digit postal code starting with digits 1-9 (e.g., 302001, 110001, 400001)."
        )
    return val_clean


# 7. Booking Dates Validator & Flexible Parser
def parse_flexible_date(date_val):
    """
    Parses date safely from multiple formats:
    - date or datetime instances
    - ISO 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS...'
    - Indian standard 'DD-MM-YYYY'
    - Slash formats 'DD/MM/YYYY', 'YYYY/MM/DD'
    Returns date object, or None if unparseable / empty.
    """
    if not date_val:
        return None
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
    
    val_str = str(date_val).split('T')[0].strip()
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            pass
    return None

def validate_check_in_out_dates(check_in, check_out):
    """
    Validates check-in and check-out dates according to standard hotel rules:
    - Supports YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, etc.
    - check-in cannot be before today
    - check-out must be strictly after check-in
    - maximum duration cannot exceed 90 days
    """
    parsed_cin = parse_flexible_date(check_in)
    parsed_cout = parse_flexible_date(check_out)

    if not parsed_cin:
        raise serializers.ValidationError({
            "check_in": f"Invalid check-in date format: '{check_in}'. Expected YYYY-MM-DD or DD-MM-YYYY."
        })
    if not parsed_cout:
        raise serializers.ValidationError({
            "check_out": f"Invalid check-out date format: '{check_out}'. Expected YYYY-MM-DD or DD-MM-YYYY."
        })

    today = date.today()
    if parsed_cin < today:
        raise serializers.ValidationError({
            "check_in": f"Check-in date ({parsed_cin}) cannot be in the past. Today's date is {today}."
        })

    if parsed_cout <= parsed_cin:
        raise serializers.ValidationError({
            "check_out": f"Check-out date ({parsed_cout}) must be at least one day after Check-in date ({parsed_cin})."
        })

    stay_duration = (parsed_cout - parsed_cin).days
    if stay_duration > 90:
        raise serializers.ValidationError({
            "check_out": "Maximum allowable stay duration is 90 days for standard reservations."
        })

    return parsed_cin, parsed_cout


# 8. Date of Birth Age Validator (Indian legal adult age 18)
def validate_minimum_age(dob, min_age=18):
    if not dob:
        return None
    if isinstance(dob, str):
        dob = datetime.strptime(dob, '%Y-%m-%d').date()
    
    today = date.today()
    calculated_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if calculated_age < min_age:
        raise serializers.ValidationError(
            f"Age verification failed: Account holders and primary guests must be at least {min_age} years old."
        )
    return dob


# 9. Hotel Name Validator
def validate_hotel_name(value):
    """
    Validates hotel name:
    - Cannot be empty or whitespace only.
    - Minimum length: 3 characters.
    - Cannot contain numbers (0-9). Numbers are strictly forbidden in hotel name.
    - Must contain only letters, spaces, hyphens, dots, apostrophes, and ampersands (&).
    - Must contain at least 2 alphabetic letters.
    """
    if not value or not str(value).strip():
        raise serializers.ValidationError("Hotel name is required and cannot be empty.")
    
    val_clean = str(value).strip()
    
    if len(val_clean) < 3:
        raise serializers.ValidationError("Hotel name must be at least 3 characters long.")
    
    # Strictly forbid numbers in hotel name
    if re.search(r'\d', val_clean):
        raise serializers.ValidationError(
            f"Numbers are not allowed in hotel name. You entered '{val_clean}'. "
            "Hotel name can only contain letters and spaces (e.g., 'Hotel Taj Palace', 'The Grand Resort')."
        )
    
    # Must contain only alphabetic letters, spaces, dots, hyphens, apostrophes, ampersands
    if not re.match(r"^[a-zA-Z\s\.\-\'\&]+$", val_clean):
        raise serializers.ValidationError(
            f"Invalid characters in hotel name '{val_clean}'. "
            "Hotel name can only contain alphabetic letters, spaces, dots, hyphens, and ampersands."
        )

    letters = re.findall(r'[a-zA-Z]', val_clean)
    if len(letters) < 2:
        raise serializers.ValidationError(
            "Hotel name must contain valid alphabetic letters representing the property name."
        )

    return val_clean


# 10. Hotel Address Validator
def validate_hotel_address(value):
    """
    Validates hotel address:
    - Cannot be empty or whitespace only.
    - Minimum length: 5 characters.
    - Alphanumeric support: both numbers and alphabets are supported and encouraged
      (e.g., 'Plot 42, MG Road, Near City Mall', 'Flat 101, Sunshine Heights, Sector 14').
    - Cannot be purely numeric (e.g. '123456' is strictly rejected as an address).
    - Cannot consist only of punctuation or special characters (e.g., ',,,---').
    - Must contain street/locality/building details with letters (at least 3 letters).
    """
    if not value or not str(value).strip():
        raise serializers.ValidationError("Address is required and cannot be empty.")
    
    val_clean = str(value).strip()
    
    if len(val_clean) < 5:
        raise serializers.ValidationError("Address must be at least 5 characters long.")
    
    # Pure numeric check
    if val_clean.isdigit():
        raise serializers.ValidationError(
            f"Invalid address '{val_clean}'. Address cannot be purely numeric. "
            "It must include street, locality, or building details (e.g., 'Plot 42, MG Road, Near City Center')."
        )
    
    # Must contain at least 3 alphabetic letters for meaningful location info
    letters = re.findall(r'[a-zA-Z]', val_clean)
    if len(letters) < 3:
        raise serializers.ValidationError(
            f"Invalid address '{val_clean}'. Address must contain meaningful street/locality text with letters. "
            "Alphanumeric details like plot numbers and street names are both supported (e.g., '123 MG Road, Near Metro Station')."
        )
    
    return val_clean


# 11. City / State Name Validator
def validate_city_or_state(value, field_name="City"):
    """
    Validates city or state name:
    - Cannot be purely numeric.
    - Must contain at least 2 alphabetic letters.
    """
    if not value or not str(value).strip():
        raise serializers.ValidationError(f"{field_name} is required and cannot be empty.")
    
    val_clean = str(value).strip()
    if len(val_clean) < 2:
        raise serializers.ValidationError(f"{field_name} must be at least 2 characters long.")
    
    letters = re.findall(r'[a-zA-Z]', val_clean)
    if len(letters) < 2:
        raise serializers.ValidationError(
            f"Invalid {field_name.lower()} '{val_clean}'. Must contain valid alphabetic characters (e.g., 'Mumbai', 'Rajasthan')."
        )
    return val_clean



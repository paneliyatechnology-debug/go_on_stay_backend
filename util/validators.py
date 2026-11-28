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


# 12. Media & Upload Validators (P3-FINDING-08)
def validate_upload_image(file):
    """
    Validates uploaded hotel/room/avatar images:
    - Maximum file size: 5 MB
    - Allowed extensions: .jpg, .jpeg, .png, .webp
    """
    if not file:
        return file
    
    max_size = 5 * 1024 * 1024  # 5 MB
    file_size = getattr(file, 'size', 0)
    if file_size > max_size:
        raise serializers.ValidationError(
            f"Image file size cannot exceed 5MB. Uploaded size: {file_size / (1024 * 1024):.2f}MB."
        )
    
    import os
    import uuid
    ext = os.path.splitext(getattr(file, 'name', ''))[1].lower()
    allowed = ['.jpg', '.jpeg', '.png', '.webp']
    if ext not in allowed:
        raise serializers.ValidationError(
            f"Invalid image format '{ext}'. Allowed image formats: {', '.join(allowed)}."
        )
    # Defense-in-depth: Randomize filename with UUID to prevent exposure of client private filenames or paths
    if hasattr(file, 'name'):
        file.name = f"{uuid.uuid4().hex}{ext}"
    return file


def validate_upload_document(file):
    """
    Validates uploaded verification/KYC documents:
    - Maximum file size: 10 MB
    - Allowed extensions: .pdf, .jpg, .jpeg, .png, .webp
    - Sanitizes filename to secure UUID
    """
    if not file:
        return file
    
    max_size = 10 * 1024 * 1024  # 10 MB
    file_size = getattr(file, 'size', 0)
    if file_size > max_size:
        raise serializers.ValidationError(
            f"Document file size cannot exceed 10MB. Uploaded size: {file_size / (1024 * 1024):.2f}MB."
        )
    
    import os
    import uuid
    ext = os.path.splitext(getattr(file, 'name', ''))[1].lower()
    allowed = ['.pdf', '.jpg', '.jpeg', '.png', '.webp']
    if ext not in allowed:
        raise serializers.ValidationError(
            f"Invalid document format '{ext}'. Allowed document formats: {', '.join(allowed)}."
        )
    # Defense-in-depth: Randomize filename with UUID to prevent exposure of client private filenames or paths
    if hasattr(file, 'name'):
        file.name = f"{uuid.uuid4().hex}{ext}"
    return file


# 13. Guest & Room Occupancy Validator (Adults, Children, Rooms Required)
def validate_occupancy(adults=None, children=None, rooms=None, total_guests=None, room=None):
    """
    Validates hotel occupancy across all 3 parts:
      Part 1: Adults (Ages 13+)
      Part 2: Children (Ages 2-12)
      Part 3: Rooms Required (Number of rooms needed)

    Validation Rules:
      1. Adults:
         - Must be an integer >= 1 (At least 1 adult is mandatory; minors cannot stay alone).
         - 1 person / adult can book as many rooms as needed (no 1 room = 1 adult restriction).
      2. Children:
         - Must be an integer >= 0.
         - Children cannot stay without an adult (if children > 0, adults must be >= 1).
      3. Rooms Required:
         - Must be an integer >= 1.
         - Maximum 30 rooms per single reservation.
      4. Room Capacity Limits:
         - If a specific Room instance is provided:
           - Total guests (adults + children) cannot exceed rooms * (room.capacity_adults + room.capacity_children).
           - Adults cannot exceed rooms * (room.capacity_adults + 1) [allowing max 1 extra adult if hotel supports it].
         - If generic search (no room instance):
           - Total guests cannot exceed rooms * 6.
           - Adults cannot exceed rooms * 4.

    Returns:
      dict: {'adults': int, 'children': int, 'rooms': int, 'total_guests': int}
    """
    import math

    # 1. Parse Rooms
    if rooms is None or str(rooms).strip() == '':
        rooms_val = 1
    else:
        try:
            rooms_val = int(str(rooms).strip())
        except (ValueError, TypeError):
            raise serializers.ValidationError({
                "rooms": f"Invalid number of rooms '{rooms}'. Must be a valid positive integer."
            })

    if rooms_val < 1:
        raise serializers.ValidationError({
            "rooms": "Number of rooms must be at least 1."
        })

    if rooms_val > 30:
        raise serializers.ValidationError({
            "rooms": "A maximum of 30 rooms can be booked in a single reservation. For larger group bookings, please contact GoOnStay Support."
        })

    # 2. Parse Children
    if children is None or str(children).strip() == '':
        children_val = 0
    else:
        try:
            children_val = int(str(children).strip())
        except (ValueError, TypeError):
            raise serializers.ValidationError({
                "children": f"Invalid number of children '{children}'. Must be a valid integer."
            })

    if children_val < 0:
        raise serializers.ValidationError({
            "children": "Number of children cannot be negative."
        })

    # 3. Parse Adults & Total Guests
    adults_parsed = None
    if adults is not None and str(adults).strip() != '':
        try:
            adults_parsed = int(str(adults).strip())
        except (ValueError, TypeError):
            raise serializers.ValidationError({
                "adults": f"Invalid number of adults '{adults}'. Must be a valid positive integer."
            })

    guests_parsed = None
    if total_guests is not None and str(total_guests).strip() != '':
        try:
            guests_parsed = int(str(total_guests).strip())
        except (ValueError, TypeError):
            raise serializers.ValidationError({
                "guests": f"Invalid number of guests '{total_guests}'. Must be a valid positive integer."
            })

    # Resolve Adults and Total Guests
    if adults_parsed is not None:
        adults_val = adults_parsed
        if guests_parsed is not None:
            if guests_parsed < adults_val:
                raise serializers.ValidationError({
                    "guests": f"Total guests ({guests_parsed}) cannot be less than the number of adults ({adults_val})."
                })
            total_guests_val = adults_val + children_val
        else:
            total_guests_val = adults_val + children_val
    elif guests_parsed is not None:
        # Infer adults from total guests - children
        if guests_parsed < children_val:
            raise serializers.ValidationError({
                "guests": f"Total guests ({guests_parsed}) cannot be less than number of children ({children_val})."
            })
        adults_val = guests_parsed - children_val
        total_guests_val = guests_parsed
    else:
        # Neither adults nor total_guests specified
        adults_val = max(1, rooms_val)
        total_guests_val = adults_val + children_val

    # --- PART 1 VALIDATION: Adults ---
    if adults_val < 1:
        raise serializers.ValidationError({
            "adults": "At least 1 adult (age 13+) is required. Minors cannot book or stay in a hotel room without an adult."
        })

    # --- PART 2 VALIDATION: Children ---
    if children_val > 0 and adults_val < 1:
        raise serializers.ValidationError({
            "children": "Children (ages 2-12) must be accompanied by at least one adult."
        })

    # --- CAPACITY CHECKS (Combined 3 parts) ---
    if room is not None:
        cap_adults = getattr(room, 'capacity_adults', 2) or 2
        cap_children = getattr(room, 'capacity_children', 1) or 0
        room_title = getattr(room, 'title', 'Selected Room')
        max_room_cap = cap_adults + cap_children
        total_max_cap = rooms_val * max_room_cap

        if total_guests_val > total_max_cap:
            min_rooms_needed = math.ceil(total_guests_val / max(1, max_room_cap))
            raise serializers.ValidationError({
                "number_of_guests": (
                    f"Total guests ({total_guests_val}) exceed maximum capacity ({total_max_cap}) for {rooms_val} room(s) of type '{room_title}'. "
                    f"Each room accommodates up to {max_room_cap} guests ({cap_adults} adults, {cap_children} children). "
                    f"Please select at least {min_rooms_needed} room(s)."
                )
            })

        # Check adult capacity specifically (children capacity cannot be used for extra adults)
        allowed_adults = rooms_val * (cap_adults + (1 if getattr(room, 'extra_guest_price', 0) else 0))
        if adults_val > allowed_adults:
            min_rooms_for_adults = math.ceil(adults_val / max(1, cap_adults))
            raise serializers.ValidationError({
                "adults": (
                    f"{adults_val} adults exceed the adult capacity for {rooms_val} room(s) of type '{room_title}' (maximum {allowed_adults} adults). "
                    f"Please select at least {min_rooms_for_adults} room(s)."
                )
            })
    else:
        # Generic Search / No specific room yet
        if total_guests_val > rooms_val * 6:
            min_rooms_needed = math.ceil(total_guests_val / 4)
            raise serializers.ValidationError({
                "rooms": (
                    f"{total_guests_val} guests cannot be accommodated in {rooms_val} room(s). "
                    f"Standard rooms accommodate up to 4-5 guests. Please select at least {min_rooms_needed} room(s)."
                )
            })

        if adults_val > rooms_val * 4:
            min_rooms_for_adults = math.ceil(adults_val / 3)
            raise serializers.ValidationError({
                "rooms": (
                    f"{adults_val} adults cannot be accommodated in {rooms_val} room(s). "
                    f"Maximum 4 adults allowed per standard room. Please select at least {min_rooms_for_adults} room(s)."
                )
            })

    return {
        'adults': adults_val,
        'children': children_val,
        'rooms': rooms_val,
        'total_guests': total_guests_val
    }




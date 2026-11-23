from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from util.validators import (
    clean_indian_phone, clean_email,
    validate_indian_bank_account, validate_indian_ifsc,
    validate_indian_upi, validate_minimum_age
)

User = get_user_model()

class HybridAvatarField(serializers.Field):
    """
    Field that accepts both an uploaded file (traditional multipart form)
    and a Cloudinary direct upload string URL (e.g. https://res.cloudinary.com/...).
    """
    def to_internal_value(self, data):
        if not data:
            return None
        if isinstance(data, str):
            val = data.strip()
            if not val:
                return None
            if val.startswith(('http://', 'https://')):
                return val
            if val.startswith(('users/avatars/', '/media/')):
                return val
            raise serializers.ValidationError("Invalid image URL or path format.")
        from django.core.files.uploadedfile import UploadedFile
        if isinstance(data, UploadedFile):
            return data
        raise serializers.ValidationError("Expected an image file or a valid Cloudinary image URL.")

    def to_representation(self, value):
        if not value:
            return None
        val_str = str(value)
        if val_str.startswith(('http://', 'https://')):
            return val_str
        if hasattr(value, 'url'):
            request = self.context.get('request', None)
            if request:
                return request.build_absolute_uri(value.url)
            return value.url
        return val_str

class UserSerializer(serializers.ModelSerializer):
    payout_account = serializers.SerializerMethodField()
    hotels_count = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    razorpay_key_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_custom_razorpay_keys = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'subscription_tier', 'phone_number', 'dob', 'avatar', 'bio',
            'preferred_language', 'preferred_currency', 'is_email_verified',
            'is_blocked', 'is_staff', 'is_superuser',
            'razorpay_key_id', 'razorpay_key_secret', 'has_custom_razorpay_keys',
            'payout_account', 'hotels_count',
            'created_at', 'updated_at'
        )
        read_only_fields = ('id', 'is_blocked', 'is_email_verified', 'created_at', 'updated_at')
        extra_kwargs = {
            'razorpay_key_secret': {'write_only': True}
        }

    def get_has_custom_razorpay_keys(self, obj):
        return bool(obj.razorpay_key_id and obj.razorpay_key_secret)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Defense-in-depth: Never expose merchant Razorpay secret in API serialization responses
        ret.pop('razorpay_key_secret', None)
        return ret

    def get_avatar(self, obj):
        if not obj.avatar:
            return None
        val_str = str(obj.avatar)
        if val_str.startswith(('http://', 'https://')):
            return val_str
        if hasattr(obj.avatar, 'url'):
            request = self.context.get('request', None)
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return val_str

    def get_hotels_count(self, obj):
        if hasattr(obj, 'hotels'):
            return obj.hotels.count()
        return 0

    def get_payout_account(self, obj):
        acc = getattr(obj, 'payout_account', None)
        if not acc:
            return None
        return {
            'id': acc.id,
            'payout_method': acc.payout_method,
            'account_holder_name': acc.account_holder_name,
            'bank_name': acc.bank_name,
            'masked_account_number': acc.masked_account_number,
            'masked_upi_id': acc.masked_upi_id,
            'ifsc_code': acc.ifsc_code,
            'destination_summary': acc.destination_summary,
            'is_verified': acc.is_verified,
            'verification_status': acc.verification_status,
        }

class RegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # Hotel Owner Onboarding Payout Fields
    payout_method = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    account_holder_name = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    bank_name = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    account_number = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    ifsc_code = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    upi_id = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    # Hotel Owner Onboarding Property Fields (Step 1)
    hotel_name = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    property_type = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    city = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    state = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    address = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    zip_code = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    razorpay_key_secret = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = (
            'username', 'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'role', 'phone_number',
            'dob', 'preferred_language', 'preferred_currency',
            'razorpay_key_id', 'razorpay_key_secret',
            'payout_method', 'account_holder_name', 'bank_name',
            'account_number', 'ifsc_code', 'upi_id',
            'hotel_name', 'property_type', 'city', 'state', 'address', 'zip_code'
        )
        extra_kwargs = {
            'razorpay_key_secret': {'write_only': True}
        }

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'phone' in data and not data.get('phone_number'):
            data['phone_number'] = data['phone']
        if 'email' in data and isinstance(data['email'], str):
            data['email'] = data['email'].lower().strip()
        
        # If user provides full 'name' on registration, map to first_name & last_name
        is_host = str(data.get('role', '')).upper() in [User.ROLE_HOTEL_OWNER, 'HOST', 'OWNER']
        if data.get('name') and not data.get('first_name') and not is_host:
            name_parts = str(data['name']).strip().split(' ', 1)
            data['first_name'] = name_parts[0]
            if len(name_parts) > 1:
                data['last_name'] = name_parts[1]

        # Map frontend property fields ONLY IF host registration or provided
        hname = data.get('hotel_name') or data.get('hotelName')
        if not hname and is_host:
            hname = data.get('name')
        if hname:
            data['hotel_name'] = hname

        addr = (
            data.get('address') or
            data.get('property_address') or
            data.get('full_property_address') or
            data.get('full_address') or
            data.get('propertyAddress')
        )
        if addr:
            data['address'] = addr

        dest = data.get('destination_city') or data.get('destination') or data.get('destinationCity')
        if dest and not data.get('city'):
            if ',' in dest:
                parts = [p.strip() for p in dest.split(',')]
                data['city'] = parts[0]
                if not data.get('state') and len(parts) > 1:
                    data['state'] = parts[1]
            else:
                data['city'] = dest

        # Remove None values for all optional fields so DRF doesn't fail with 'This field may not be null'
        for k in list(data.keys()):
            if data[k] is None:
                data.pop(k)

        return super().to_internal_value(data)

    def validate(self, attrs):
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')
        if password_confirm and password != password_confirm:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        
        # Strict Email validation
        raw_email = attrs.get('email')
        try:
            clean_mail = clean_email(raw_email)
            attrs['email'] = clean_mail
        except serializers.ValidationError as e:
            raise serializers.ValidationError({"email": e.detail})

        if User.objects.filter(email__iexact=clean_mail).exists():
            raise serializers.ValidationError({"email": "An account with this email address is already registered (as Admin, Hotel Owner, or Guest). The same email cannot be used for multiple roles or accounts."})

        # Auto-generate or sanitize username
        username = (attrs.get('username') or '').strip()
        if not username:
            import re
            base_user = re.sub(r'[^a-zA-Z0-9_]', '', clean_mail.split('@')[0]) or 'user'
            candidate = base_user
            counter = 1
            while User.objects.filter(username__iexact=candidate).exists():
                candidate = f"{base_user}{counter}"
                counter += 1
            attrs['username'] = candidate
        else:
            if User.objects.filter(username__iexact=username).exists():
                raise serializers.ValidationError({"username": "A user with that username already exists."})
            attrs['username'] = username

        # Indian Mobile Phone Validation
        phone_number = (attrs.get('phone_number') or '').strip()
        if phone_number:
            from django.db.models import Q
            try:
                clean_phone = clean_indian_phone(phone_number)
                attrs['phone_number'] = clean_phone
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"phone_number": e.detail})

            last10 = clean_phone[-10:]
            if User.objects.filter(Q(phone_number__iexact=clean_phone) | Q(phone_number__endswith=last10)).exists():
                raise serializers.ValidationError({"phone_number": "An account with this mobile number is already registered (as Admin, Hotel Owner, or Guest). The same mobile number cannot be used for multiple roles or accounts."})

        # Date of Birth Validation (Indian legal adult 18+)
        if attrs.get('dob'):
            try:
                validate_minimum_age(attrs.get('dob'))
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"dob": e.detail})

        # Indian Payout validations (if Host registration)
        if attrs.get('account_number'):
            try:
                attrs['account_number'] = validate_indian_bank_account(attrs.get('account_number'))
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"account_number": e.detail})

        if attrs.get('ifsc_code'):
            try:
                attrs['ifsc_code'] = validate_indian_ifsc(attrs.get('ifsc_code'))
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"ifsc_code": e.detail})

        if attrs.get('upi_id'):
            try:
                attrs['upi_id'] = validate_indian_upi(attrs.get('upi_id'))
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"upi_id": e.detail})

        # Hotel Property validations (for Host Onboarding / Step 1)
        raw_hotel_name = attrs.get('hotel_name')
        if raw_hotel_name:
            from util.validators import validate_hotel_name
            try:
                attrs['hotel_name'] = validate_hotel_name(raw_hotel_name)
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"hotel_name": e.detail})

        raw_address = attrs.get('address')
        if raw_address:
            from util.validators import validate_hotel_address
            try:
                attrs['address'] = validate_hotel_address(raw_address)
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"address": e.detail})

        raw_city = attrs.get('city')
        if raw_city:
            from util.validators import validate_city_or_state
            try:
                attrs['city'] = validate_city_or_state(raw_city, "City")
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"city": e.detail})

        raw_zip = attrs.get('zip_code')
        if raw_zip:
            from util.validators import validate_indian_pincode
            try:
                attrs['zip_code'] = validate_indian_pincode(raw_zip)
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"zip_code": e.detail})
        
        # Don't allow creating admin or super admin via public registration
        if attrs.get('role') in [User.ROLE_ADMIN, User.ROLE_SUPER_ADMIN]:
            attrs['role'] = User.ROLE_CUSTOMER

        return attrs

    def create(self, validated_data):
        payout_method = validated_data.pop('payout_method', None)
        account_holder_name = validated_data.pop('account_holder_name', None)
        bank_name = validated_data.pop('bank_name', None)
        account_number = validated_data.pop('account_number', None)
        ifsc_code = validated_data.pop('ifsc_code', None)
        upi_id = validated_data.pop('upi_id', None)

        # Hotel Property fields
        hotel_name = validated_data.pop('hotel_name', None)
        property_type = validated_data.pop('property_type', None)
        city = validated_data.pop('city', None)
        state = validated_data.pop('state', None)
        address = validated_data.pop('address', None)
        zip_code = validated_data.pop('zip_code', None)

        validated_data.pop('password_confirm', None)
        password = validated_data.pop('password')
        from django.db import IntegrityError
        try:
            user = User.objects.create(**validated_data)
        except IntegrityError as err:
            err_str = str(err).lower()
            if 'email' in err_str:
                raise serializers.ValidationError({"email": ["A user with this email address already exists."]})
            if 'phone' in err_str:
                raise serializers.ValidationError({"phone_number": ["This mobile phone number is already registered."]})
            raise serializers.ValidationError({"non_field_errors": ["A database constraint conflict occurred. Please verify your details."]})

        user.set_password(password)
        user.is_email_verified = True
        user.save()

        # If user is a HOTEL_OWNER and hotel property details are provided, automatically create Hotel
        created_hotel = None
        if user.role == User.ROLE_HOTEL_OWNER and (hotel_name or address):
            from hotels.models import Hotel
            prop_type = (property_type or 'HOTEL').upper()
            valid_types = [t[0] for t in Hotel.PROPERTY_TYPE_CHOICES]
            if prop_type not in valid_types:
                prop_type = Hotel.PROPERTY_TYPE_HOTEL

            created_hotel = Hotel.objects.create(
                owner=user,
                name=hotel_name or f"{user.get_full_name() or user.username}'s Hotel",
                property_type=prop_type,
                city=city or 'Jaipur',
                state=state or 'Rajasthan',
                address=address or 'Plot 1, Main Road',
                zip_code=zip_code or '302001',
                country='India',
                status=Hotel.STATUS_SUBMITTED,
                is_approved=False
            )
        user._created_hotel = created_hotel

        # If hotel owner onboarding provided payout details, register HostPayoutAccount
        if user.role == User.ROLE_HOTEL_OWNER and (account_number or upi_id):
            from payments.models import HostPayoutAccount
            from django.utils import timezone
            import uuid
            
            clean_acc = account_number.strip() if account_number else None
            clean_ifsc = ifsc_code.strip().upper() if ifsc_code else None
            clean_upi = upi_id.strip().lower() if upi_id else None

            HostPayoutAccount.objects.create(
                user=user,
                payout_method=payout_method or (HostPayoutAccount.METHOD_UPI if clean_upi else HostPayoutAccount.METHOD_BANK),
                account_holder_name=account_holder_name or user.get_full_name() or user.username,
                bank_name=bank_name or 'Bank',
                account_number=clean_acc,
                ifsc_code=clean_ifsc,
                upi_id=clean_upi,
                is_verified=True,
                verification_status=HostPayoutAccount.STATUS_VERIFIED,
                fund_account_id=f"fa_reg_{uuid.uuid4().hex[:10]}",
                verified_at=timezone.now()
            )

        return user

class UserProfileUpdateSerializer(serializers.ModelSerializer):
    avatar = HybridAvatarField(required=False, allow_null=True)
    razorpay_key_secret = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = (
            'first_name', 'last_name', 'email', 'phone_number', 'dob',
            'avatar', 'bio', 'preferred_language', 'preferred_currency',
            'razorpay_key_id', 'razorpay_key_secret'
        )
        extra_kwargs = {
            'razorpay_key_secret': {'write_only': True}
        }

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, 'copy') else dict(data)
        if 'phone' in data and not data.get('phone_number'):
            data['phone_number'] = data['phone']
        if 'email' in data and isinstance(data['email'], str):
            data['email'] = data['email'].lower().strip()
        if 'avatar_url' in data and not data.get('avatar'):
            data['avatar'] = data['avatar_url']
        if 'name' in data and not (data.get('first_name') or data.get('last_name')):
            raw_name = str(data['name']).strip()
            parts = raw_name.split(' ', 1)
            data['first_name'] = parts[0]
            data['last_name'] = parts[1] if len(parts) > 1 else ''
        return super().to_internal_value(data)

    def validate_email(self, value):
        if value:
            val_clean = clean_email(value)
            user = self.instance
            qs = User.objects.exclude(pk=user.pk if user else None)
            if qs.filter(email__iexact=val_clean).exists():
                raise serializers.ValidationError("An account with this email address is already registered.")
            return val_clean
        return value

    def validate_phone_number(self, value):
        if value:
            from django.db.models import Q
            val_clean = clean_indian_phone(value)
            user = self.instance
            qs = User.objects.exclude(pk=user.pk if user else None)
            last10 = val_clean[-10:]
            if qs.filter(Q(phone_number__iexact=val_clean) | Q(phone_number__endswith=last10)).exists():
                raise serializers.ValidationError("An account with this mobile number is already registered.")
            return val_clean
        return value

    def validate_dob(self, value):
        if value:
            return validate_minimum_age(value)
        return value

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])

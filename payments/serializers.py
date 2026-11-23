from rest_framework import serializers
from .models import (
    Payment, Refund, WebhookEvent, HostPayoutAccount, HostEarning,
    HostPayout, PlatformSetting, SupportTicket, TicketMessage,
    CustomerHotelMessage, AuditLog
)
from bookings.models import Booking
from users.serializers import UserSerializer

class PaymentSerializer(serializers.ModelSerializer):
    booking_id = serializers.CharField(source='booking.booking_id', read_only=True)
    customer_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    hotel_name = serializers.CharField(source='booking.hotel.name', read_only=True)
    host_name = serializers.CharField(source='booking.hotel.owner.get_full_name', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'booking', 'booking_id', 'user', 'customer_name', 'user_email',
            'hotel_name', 'host_name', 'razorpay_order_id',
            'razorpay_payment_id', 'amount', 'currency', 'status',
            'payment_method', 'failure_reason', 'error_code',
            'paid_at', 'is_duplicate_captured', 'review_notes', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class RefundSerializer(serializers.ModelSerializer):
    booking_id = serializers.CharField(source='booking.booking_id', read_only=True)
    cancellation_status = serializers.CharField(source='booking.booking_status', read_only=True)
    refund_status = serializers.CharField(source='status', read_only=True)
    refund_amount = serializers.DecimalField(source='amount', max_digits=12, decimal_places=2, read_only=True)
    provider_refund_id = serializers.CharField(source='razorpay_refund_id', read_only=True)
    customer_name = serializers.CharField(source='booking.customer.get_full_name', read_only=True)
    customer_email = serializers.CharField(source='booking.customer.email', read_only=True)
    guest_name = serializers.CharField(source='booking.guest_name', read_only=True)
    hotel_name = serializers.CharField(source='booking.hotel.name', read_only=True)
    check_in = serializers.DateField(source='booking.check_in', read_only=True)
    total_amount = serializers.DecimalField(source='booking.total_amount', max_digits=12, decimal_places=2, read_only=True)
    cancellation_fee_percentage = serializers.DecimalField(source='booking.cancellation_fee_percentage', max_digits=5, decimal_places=2, read_only=True)
    cancellation_charge = serializers.DecimalField(source='booking.cancellation_charge', max_digits=12, decimal_places=2, read_only=True)
    refundable_amount = serializers.DecimalField(source='booking.refundable_amount', max_digits=12, decimal_places=2, read_only=True)
    applied_cancellation_policy = serializers.CharField(source='booking.applied_cancellation_policy', read_only=True)

    payout_eligibility = serializers.SerializerMethodField()
    host_payable_amount = serializers.SerializerMethodField()
    updated_timestamps = serializers.SerializerMethodField()
    processed_by_name = serializers.CharField(source='processed_by.get_full_name', read_only=True)
    customer_account_number = serializers.SerializerMethodField()
    customer_upi_id = serializers.SerializerMethodField()
    customer_payout_details = serializers.SerializerMethodField()

    class Meta:
        model = Refund
        fields = [
            'id', 'booking', 'booking_id', 'cancellation_status', 'refund_status',
            'amount', 'refund_amount', 'refund_mode', 'provider_refund_id', 'razorpay_refund_id',
            'payout_reference_id', 'payout_eligibility', 'host_payable_amount', 'updated_timestamps',
            'idempotency_key', 'failure_reason', 'provider_status', 'retry_count',
            'customer_name', 'customer_email', 'guest_name', 'hotel_name', 'check_in',
            'total_amount', 'cancellation_fee_percentage', 'cancellation_charge',
            'refundable_amount', 'applied_cancellation_policy', 'payment',
            'razorpay_payment_id', 'currency', 'reason', 'admin_notes', 'status',
            'customer_account_holder', 'customer_bank_name', 'customer_account_number',
            'customer_ifsc_code', 'customer_upi_id', 'customer_payout_details',
            'processed_by', 'processed_by_name',
            'created_at', 'processed_at', 'failed_at'
        ]
        read_only_fields = fields

    def _is_admin(self):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        user = request.user
        return bool(user.is_staff or user.is_superuser or getattr(user, 'role', '') in ['ADMIN', 'SUPER_ADMIN'])

    def get_customer_account_number(self, obj):
        if not obj.customer_account_number:
            return None
        if self._is_admin():
            return obj.customer_account_number
        acc = obj.customer_account_number
        return f"{'*' * max(0, len(acc) - 4)}{acc[-4:]}"

    def get_customer_upi_id(self, obj):
        if not obj.customer_upi_id:
            return None
        if self._is_admin():
            return obj.customer_upi_id
        upi = obj.customer_upi_id
        if '@' in upi:
            parts = upi.split('@')
            return f"{parts[0][:2]}***@{parts[1]}"
        return f"{upi[:2]}***"

    def get_customer_payout_details(self, obj):
        if not (obj.customer_account_number or obj.customer_upi_id):
            return None
        return {
            'refund_mode': obj.refund_mode,
            'account_holder_name': obj.customer_account_holder,
            'bank_name': obj.customer_bank_name,
            'account_number_masked': self.get_customer_account_number(obj),
            'ifsc_code': obj.customer_ifsc_code,
            'upi_id_masked': self.get_customer_upi_id(obj),
            'payout_reference_id': obj.payout_reference_id
        }

    def get_payout_eligibility(self, obj):
        # Refunded / cancelled bookings are strictly NEVER eligible for host payout
        return False

    def get_host_payable_amount(self, obj):
        # Host payable amount is 0.00 for refunded / cancelled bookings
        return 0.00

    def get_updated_timestamps(self, obj):
        ts = obj.processed_at or obj.failed_at or obj.created_at
        return ts.isoformat() if ts else None


class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = ['id', 'event_id', 'event_type', 'payload', 'processed', 'processed_at', 'created_at']
        read_only_fields = fields


class HostPayoutAccountSerializer(serializers.ModelSerializer):
    masked_account_number = serializers.CharField(read_only=True)
    masked_upi_id = serializers.CharField(read_only=True)
    destination_summary = serializers.CharField(read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    # Write-only fields for secure entry
    account_number = serializers.CharField(write_only=True, required=False, allow_blank=True)
    confirm_account_number = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = HostPayoutAccount
        fields = [
            'id', 'user', 'user_name', 'user_email', 'payout_method',
            'account_holder_name', 'bank_name', 'account_number', 'confirm_account_number',
            'ifsc_code', 'upi_id', 'is_verified', 'verification_status',
            'masked_account_number', 'masked_upi_id', 'destination_summary',
            'fund_account_id', 'verification_error', 'verified_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'is_verified', 'verification_status', 'fund_account_id', 'verification_error', 'verified_at', 'created_at', 'updated_at']

    def validate(self, attrs):
        method = attrs.get('payout_method') or (self.instance.payout_method if self.instance else HostPayoutAccount.METHOD_BANK)
        
        if method == HostPayoutAccount.METHOD_BANK:
            acc_num = attrs.get('account_number')
            confirm_acc = attrs.get('confirm_account_number')
            if not self.instance and not acc_num:
                raise serializers.ValidationError({"account_number": "Bank account number is required."})
            if acc_num and confirm_acc and acc_num.strip() != confirm_acc.strip():
                raise serializers.ValidationError({"confirm_account_number": "Account numbers do not match."})
            ifsc = attrs.get('ifsc_code') or (self.instance.ifsc_code if self.instance else '')
            if not ifsc or len(ifsc.strip()) != 11:
                raise serializers.ValidationError({"ifsc_code": "Enter a valid 11-character Indian IFSC code (e.g. HDFC0001234)."})
        elif method == HostPayoutAccount.METHOD_UPI:
            upi = attrs.get('upi_id') or (self.instance.upi_id if self.instance else '')
            if not upi or '@' not in upi:
                raise serializers.ValidationError({"upi_id": "Enter a valid UPI ID (e.g. name@okhdfcbank)."})
        return attrs


class HostEarningSerializer(serializers.ModelSerializer):
    booking_id = serializers.CharField(source='booking.booking_id', read_only=True)
    cancellation_status = serializers.CharField(source='booking.booking_status', read_only=True)
    hotel_id = serializers.IntegerField(source='booking.hotel.id', read_only=True)
    hotel_name = serializers.CharField(source='booking.hotel.name', read_only=True)
    hotel_city = serializers.CharField(source='booking.hotel.city', read_only=True)
    room_title = serializers.CharField(source='booking.room.title', read_only=True)
    guest_name = serializers.CharField(source='booking.guest_name', read_only=True)
    check_in = serializers.DateField(source='booking.check_in', read_only=True)
    check_out = serializers.DateField(source='booking.check_out', read_only=True)
    booking_status = serializers.CharField(source='booking.booking_status', read_only=True)
    payment_status = serializers.CharField(source='booking.payment_status', read_only=True)
    host_name = serializers.CharField(source='host.get_full_name', read_only=True)
    host_email = serializers.CharField(source='host.email', read_only=True)
    payout_id = serializers.CharField(source='payout.payout_id', read_only=True)
    payment_id = serializers.SerializerMethodField()
    razorpay_payment_id = serializers.SerializerMethodField()

    is_eligible = serializers.SerializerMethodField()
    payout_eligibility = serializers.SerializerMethodField()
    host_payable_amount = serializers.SerializerMethodField()
    refund_status = serializers.SerializerMethodField()
    provider_refund_id = serializers.SerializerMethodField()
    updated_timestamps = serializers.SerializerMethodField()
    hold_reasons = serializers.SerializerMethodField()
    destination_summary = serializers.SerializerMethodField()
    host_payout_account = serializers.SerializerMethodField()

    class Meta:
        model = HostEarning
        fields = [
            'id', 'host', 'host_name', 'host_email', 'booking', 'booking_id',
            'payment_id', 'razorpay_payment_id',
            'cancellation_status', 'refund_status', 'provider_refund_id',
            'payout_eligibility', 'host_payable_amount', 'updated_timestamps',
            'hotel_id', 'hotel_name', 'hotel_city', 'room_title',
            'guest_name', 'check_in', 'check_out',
            'booking_status', 'payment_status',
            'gross_amount', 'platform_fee_percent', 'platform_fee',
            'tax', 'refund_amount', 'net_amount',
            'status', 'holding_period_days', 'hold_until', 'hold_reason',
            'is_disputed', 'dispute_reason', 'payout', 'payout_id',
            'is_eligible', 'hold_reasons', 'destination_summary',
            'host_payout_account',
            'available_at', 'settled_at', 'created_at', 'updated_at'
        ]
        read_only_fields = fields

    def get_payment_id(self, obj):
        if not obj.booking:
            return None
        captured = obj.booking.payments.filter(status='CAPTURED').first() or obj.booking.payments.first()
        return captured.razorpay_payment_id if (captured and captured.razorpay_payment_id) else None

    def get_razorpay_payment_id(self, obj):
        return self.get_payment_id(obj)

    def get_is_eligible(self, obj):
        is_eligible, _ = obj.calculate_eligibility()
        return is_eligible

    def get_payout_eligibility(self, obj):
        is_eligible, _ = obj.calculate_eligibility()
        return is_eligible

    def get_host_payable_amount(self, obj):
        is_eligible, _ = obj.calculate_eligibility()
        return float(obj.net_amount) if is_eligible else 0.00

    def get_refund_status(self, obj):
        rf = obj.booking.refunds.order_by('-created_at').first()
        return rf.status if rf else None

    def get_provider_refund_id(self, obj):
        rf = obj.booking.refunds.order_by('-created_at').first()
        return rf.razorpay_refund_id if rf else None

    def get_updated_timestamps(self, obj):
        return obj.updated_at.isoformat() if obj.updated_at else None

    def get_hold_reasons(self, obj):
        _, reasons = obj.calculate_eligibility()
        return reasons

    def get_destination_summary(self, obj):
        acc = getattr(obj.host, 'payout_account', None)
        return acc.destination_summary if acc else 'Not Configured'

    def get_host_payout_account(self, obj):
        acc = getattr(obj.host, 'payout_account', None)
        if not acc:
            return None
        return {
            'id': acc.id,
            'payout_method': acc.payout_method,
            'account_holder_name': acc.account_holder_name,
            'bank_name': acc.bank_name,
            'masked_account_number': acc.masked_account_number,
            'ifsc_code': acc.ifsc_code,
            'masked_upi_id': acc.masked_upi_id,
            'destination_summary': acc.destination_summary,
            'is_verified': acc.is_verified,
            'verification_status': acc.verification_status,
        }


class HostPayoutSerializer(serializers.ModelSerializer):
    host_name = serializers.CharField(source='host.get_full_name', read_only=True)
    host_email = serializers.CharField(source='host.email', read_only=True)
    processed_by_name = serializers.CharField(source='processed_by.get_full_name', read_only=True)
    destination_summary = serializers.SerializerMethodField()
    earnings_count = serializers.SerializerMethodField()

    class Meta:
        model = HostPayout
        fields = [
            'id', 'payout_id', 'idempotency_key', 'host', 'host_name', 'host_email',
            'payout_account', 'destination_summary', 'amount', 'currency', 'status',
            'provider_mode', 'provider_payout_id', 'provider_status', 'provider_error',
            'setup_required_instructions', 'bank_reference', 'notes',
            'earnings_count', 'processed_by', 'processed_by_name',
            'created_at', 'processed_at'
        ]
        read_only_fields = ['id', 'payout_id', 'idempotency_key', 'created_at']

    def get_destination_summary(self, obj):
        if obj.payout_account:
            return obj.payout_account.destination_summary
        acc = getattr(obj.host, 'payout_account', None)
        return acc.destination_summary if acc else 'Unknown'

    def get_earnings_count(self, obj):
        return obj.earnings.count()


class PlatformSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSetting
        fields = [
            'id', 'commission_percentage', 'gst_tax_percentage',
            'payout_hold_days', 'payout_provider_mode', 'razorpayx_account_number',
            'razorpay_route_enabled', 'default_currency',
            'support_email', 'support_phone', 'is_maintenance_mode', 'updated_at'
        ]


class PublicPlatformSettingSerializer(serializers.ModelSerializer):
    """
    Public platform settings exposed to guests, customers, and non-admin users.
    Omits corporate banking and sensitive payout credentials (razorpayx_account_number, payout_provider_mode).
    """
    class Meta:
        model = PlatformSetting
        fields = [
            'id', 'commission_percentage', 'gst_tax_percentage',
            'default_currency', 'support_email', 'support_phone',
            'is_maintenance_mode', 'updated_at'
        ]


class InitiatePayoutRequestSerializer(serializers.Serializer):
    earning_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text="List of eligible HostEarning IDs to include in this payout"
    )
    notes = serializers.CharField(required=False, allow_blank=True, default='')
    idempotency_key = serializers.CharField(required=False, allow_blank=True)
    admin_override_hold = serializers.BooleanField(required=False, default=False)


class ToggleDisputeHoldSerializer(serializers.Serializer):
    earning_id = serializers.IntegerField(required=True)
    is_disputed = serializers.BooleanField(required=True)
    dispute_reason = serializers.CharField(required=False, allow_blank=True, default='')


from rest_framework.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from hotels.models import Hotel
from rooms.models import Room
from .validators import validate_support_attachment, sanitize_text_input

User = get_user_model()


class TicketMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    sender_role = serializers.CharField(source='sender.role', read_only=True)
    sender_email = serializers.CharField(source='sender.email', read_only=True)

    class Meta:
        model = TicketMessage
        fields = [
            'id', 'ticket', 'sender', 'sender_name', 'sender_role', 'sender_email',
            'message', 'attachment', 'attachment_url', 'created_at'
        ]
        read_only_fields = ['id', 'sender', 'created_at']

    def validate_message(self, value):
        if value:
            return sanitize_text_input(value)
        return value

    def validate_attachment(self, value):
        if value:
            validate_support_attachment(value)
        return value


class SupportTicketSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    customer_id = serializers.IntegerField(source='user.id', read_only=True)
    customer_name = serializers.CharField(source='user.get_full_name', read_only=True)
    customer_email = serializers.CharField(source='user.email', read_only=True)
    customer_phone = serializers.SerializerMethodField()
    assigned_agent_id = serializers.IntegerField(source='assigned_agent.id', read_only=True, allow_null=True)
    assigned_agent_name = serializers.CharField(source='assigned_agent.get_full_name', read_only=True)
    booking_id = serializers.CharField(source='booking.booking_id', read_only=True)
    check_in = serializers.DateField(source='booking.check_in', read_only=True, allow_null=True)
    check_out = serializers.DateField(source='booking.check_out', read_only=True, allow_null=True)
    hotel_id = serializers.IntegerField(source='hotel.id', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    room_id = serializers.IntegerField(source='room.id', read_only=True)
    room_number = serializers.SerializerMethodField()
    room_title = serializers.CharField(source='room.title', read_only=True)
    messages = TicketMessageSerializer(many=True, read_only=True)

    hotel = serializers.PrimaryKeyRelatedField(queryset=Hotel.objects.all(), required=False, allow_null=True)
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all(), required=False, allow_null=True)
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.all(), required=False, allow_null=True)
    assigned_agent = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'ticket_number', 'user', 'user_name', 'user_email',
            'customer_id', 'customer_name', 'customer_email', 'customer_phone',
            'booking', 'booking_id', 'check_in', 'check_out',
            'hotel', 'hotel_id', 'hotel_name',
            'room', 'room_id', 'room_number', 'room_title',
            'category', 'priority', 'status', 'subject', 'description',
            'attachment', 'attachment_url', 'assigned_agent', 'assigned_agent_id',
            'assigned_agent_name', 'messages', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'ticket_number', 'user', 'user_name', 'user_email',
            'customer_id', 'customer_name', 'customer_email', 'customer_phone',
            'booking_id', 'check_in', 'check_out', 'hotel_id', 'hotel_name', 'room_id',
            'room_number', 'room_title', 'assigned_agent_id', 'assigned_agent_name',
            'created_at', 'updated_at'
        ]

    def get_room_number(self, obj):
        if obj.booking and obj.booking.room_number:
            return obj.booking.room_number
        if obj.room:
            all_nums = obj.room.get_all_room_numbers()
            return all_nums[0] if all_nums else None
        return None

    def get_customer_phone(self, obj):
        request = self.context.get('request')
        req_user = getattr(request, 'user', None)
        if not req_user or not req_user.is_authenticated:
            return None
        req_role = str(getattr(req_user, 'role', '')).upper()
        is_staff_or_admin = (
            req_user.is_staff or
            getattr(req_user, 'is_superuser', False) or
            req_role in ['ADMIN', 'SUPER_ADMIN', 'SUPPORT_AGENT']
        )
        is_ticket_owner = (obj.user == req_user)
        is_hotel_owner = bool(
            obj.hotel and (
                obj.hotel.owner == req_user or
                (hasattr(req_user, 'hotels') and req_user.hotels.filter(id=obj.hotel.id).exists())
            )
        )
        is_assigned = (obj.assigned_agent == req_user)

        if is_staff_or_admin or is_ticket_owner or is_hotel_owner or is_assigned:
            return getattr(obj.user, 'phone_number', '') if obj.user else ''
        return None

    def validate_attachment(self, value):
        if value:
            validate_support_attachment(value)
        return value

    def to_internal_value(self, data):
        # Support QueryDict (multipart/form-data) and plain dict without deepcopying open file descriptors
        if hasattr(data, 'dict'):
            data = data.dict()
        else:
            data = dict(data)

        # Allow assigned_agent_id alias
        if 'assigned_agent_id' in data and 'assigned_agent' not in data:
            data['assigned_agent'] = data['assigned_agent_id']

        # Handle booking / booking_id passed as ID or alphanumeric code
        booking_raw = data.get('booking') or data.get('booking_id')
        if booking_raw not in [None, '', 'null', 'undefined']:
            if isinstance(booking_raw, str) and not booking_raw.isdigit():
                booking_obj = Booking.objects.filter(booking_id=booking_raw).first()
                if booking_obj:
                    data['booking'] = booking_obj.id
                else:
                    self._invalid_booking_ref = booking_raw
                    data['booking'] = None
            else:
                try:
                    booking_pk = int(booking_raw)
                    if not Booking.objects.filter(pk=booking_pk).exists():
                        self._invalid_booking_ref = booking_raw
                        data['booking'] = None
                    else:
                        data['booking'] = booking_pk
                except (ValueError, TypeError):
                    self._invalid_booking_ref = booking_raw
                    data['booking'] = None
        elif 'booking' in data and data['booking'] in ['', 'null', 'undefined']:
            data['booking'] = None

        return super().to_internal_value(data)

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        user_role = str(getattr(user, 'role', '')).upper() if user else ''
        is_admin_or_agent = (
            user and (
                user.is_staff or
                getattr(user, 'is_superuser', False) or
                user_role in ['ADMIN', 'SUPER_ADMIN', 'SUPPORT_AGENT']
            )
        )

        # 1. Update Restrictions for Non-Admin / Customer
        if self.instance:
            if not is_admin_or_agent:
                if 'status' in self.initial_data and self.initial_data.get('status') != self.instance.status:
                    raise PermissionDenied("Only authorized Admins and Support Agents can modify ticket status.")
                if 'assigned_agent' in self.initial_data or 'assigned_agent_id' in self.initial_data:
                    raise PermissionDenied("Only authorized Admins and Support Agents can assign tickets.")
                if 'user' in self.initial_data or 'customer' in self.initial_data or 'customer_id' in self.initial_data:
                    raise PermissionDenied("Ticket customer cannot be modified.")
                if 'booking' in self.initial_data or 'booking_id' in self.initial_data or 'hotel' in self.initial_data or 'room' in self.initial_data:
                    raise PermissionDenied("Ticket booking and hotel associations cannot be modified after creation.")

        if getattr(self, '_invalid_booking_ref', None) is not None:
            raise serializers.ValidationError({
                "booking": f"Invalid booking ID '{self._invalid_booking_ref}'. Booking does not exist.",
                "error": "Invalid booking ID or booking does not exist."
            })

        # Category validation
        valid_categories = ['BOOKING', 'PAYMENT', 'CANCELLATION', 'REFUND', 'HOTEL', 'ACCOUNT', 'TECHNICAL']
        category = attrs.get('category') or getattr(self.instance, 'category', 'BOOKING')
        if category:
            category_norm = str(category).upper()
            if category_norm not in valid_categories:
                raise serializers.ValidationError({
                    "category": f"Invalid category '{category}'. Supported categories are: {', '.join(valid_categories)}"
                })
            attrs['category'] = category_norm

        # Priority validation
        valid_priorities = ['LOW', 'MEDIUM', 'HIGH', 'URGENT']
        priority = attrs.get('priority') or getattr(self.instance, 'priority', 'MEDIUM')
        if priority:
            priority_norm = str(priority).upper()
            if priority_norm not in valid_priorities:
                raise serializers.ValidationError({
                    "priority": f"Invalid priority '{priority}'. Supported priorities are: {', '.join(valid_priorities)}"
                })
            attrs['priority'] = priority_norm

        # Status validation (for updates by Admin/Agent)
        if 'status' in attrs:
            valid_statuses = ['OPEN', 'IN_PROGRESS', 'WAITING_FOR_USER', 'RESOLVED', 'CLOSED']
            status_norm = str(attrs['status']).upper()
            if status_norm not in valid_statuses:
                raise serializers.ValidationError({
                    "status": f"Invalid status '{attrs['status']}'. Supported statuses are: {', '.join(valid_statuses)}"
                })
            attrs['status'] = status_norm

        # Booking ownership & server-side association validation on creation
        if not self.instance:
            booking = attrs.get('booking')
            if booking:
                if user and user.is_authenticated:
                    if booking.customer != user and not is_admin_or_agent:
                        raise PermissionDenied("You do not have permission to create a support ticket for another customer's booking.")
                attrs['hotel'] = booking.hotel
                attrs['room'] = booking.room
            else:
                attrs['booking'] = None
                attrs['room'] = None

            # On creation: Enforce default status and clear assigned_agent
            attrs['status'] = 'OPEN'
            attrs['assigned_agent'] = None
            if user and user.is_authenticated:
                attrs['user'] = user

        # Admin Ticket Assignment Validation
        if 'assigned_agent' in attrs:
            agent_user = attrs.get('assigned_agent')
            if agent_user is not None:
                agent_role = str(getattr(agent_user, 'role', '')).upper()
                is_hotel_owner = agent_role in ['HOTEL_OWNER', 'HOST', 'OWNER'] or (hasattr(agent_user, 'hotels') and agent_user.hotels.exists())
                is_support_staff = agent_user.is_staff or getattr(agent_user, 'is_superuser', False) or agent_role in ['ADMIN', 'SUPER_ADMIN', 'SUPPORT_AGENT']

                if not (is_hotel_owner or is_support_staff):
                    raise serializers.ValidationError({
                        "assigned_agent": f"User '{agent_user.username}' is not a registered Hotel Owner or Support Agent.",
                        "error": "The selected user is not a valid Hotel Owner or Support Agent."
                    })

                if is_hotel_owner and not is_support_staff:
                    target_hotel = self.instance.hotel if self.instance else attrs.get('hotel')
                    if not target_hotel:
                        raise serializers.ValidationError({
                            "assigned_agent": "Cannot assign a Hotel Owner to a general ticket with no associated hotel.",
                            "error": "Cannot assign a Hotel Owner to a ticket with no associated hotel."
                        })
                    owns_hotel = (target_hotel.owner == agent_user or (hasattr(agent_user, 'hotels') and agent_user.hotels.filter(id=target_hotel.id).exists()))
                    if not owns_hotel:
                        raise serializers.ValidationError({
                            "assigned_agent": f"Hotel Owner '{agent_user.username}' does not own '{target_hotel.name}'. Unrelated hotel owners cannot be assigned.",
                            "error": "Hotel Owner does not own the hotel associated with this ticket."
                        })

        # XSS Sanitization
        if 'subject' in attrs and attrs['subject']:
            attrs['subject'] = sanitize_text_input(attrs['subject'])
        if 'description' in attrs and attrs['description']:
            attrs['description'] = sanitize_text_input(attrs['description'])

        # Attachment Validation
        if 'attachment' in attrs and attrs['attachment']:
            validate_support_attachment(attrs['attachment'])

        return attrs

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        
        # Privacy-protected customer details
        ret['customer_phone'] = self.get_customer_phone(instance)
        ret['check_in'] = instance.booking.check_in if instance.booking else None
        ret['check_out'] = instance.booking.check_out if instance.booking else None
        ret['assigned_agent_id'] = instance.assigned_agent.id if instance.assigned_agent else None

        if instance.user:
            ret['customer'] = {
                'id': instance.user.id,
                'name': instance.user.get_full_name() or instance.user.username,
                'email': instance.user.email,
                'phone': self.get_customer_phone(instance),
                'phone_number': self.get_customer_phone(instance),
                'username': instance.user.username
            }
        else:
            ret['customer'] = None

        if instance.hotel:
            ret['hotel_details'] = {
                'id': instance.hotel.id,
                'name': instance.hotel.name,
                'city': getattr(instance.hotel, 'city', '')
            }
        else:
            ret['hotel_details'] = None

        if instance.room:
            ret['room_details'] = {
                'id': instance.room.id,
                'title': instance.room.title,
                'room_type': instance.room.room_type
            }
        else:
            ret['room_details'] = None

        if instance.booking:
            ret['booking_details'] = {
                'id': instance.booking.id,
                'booking_id': instance.booking.booking_id,
                'check_in': str(instance.booking.check_in),
                'check_out': str(instance.booking.check_out),
                'booking_status': instance.booking.booking_status,
                'payment_status': instance.booking.payment_status,
                'room_number': instance.booking.room_number,
                'total_amount': str(instance.booking.total_amount)
            }
        else:
            ret['booking_details'] = None

        if instance.assigned_agent:
            ret['assigned_agent_details'] = {
                'id': instance.assigned_agent.id,
                'name': instance.assigned_agent.get_full_name() or instance.assigned_agent.username,
                'email': instance.assigned_agent.email,
                'role': instance.assigned_agent.role
            }
        else:
            ret['assigned_agent_details'] = None

        # Build absolute URL for attachment if present
        request = self.context.get('request')
        if instance.attachment and hasattr(instance.attachment, 'url'):
            if request:
                ret['attachment_url'] = request.build_absolute_uri(instance.attachment.url)
            else:
                ret['attachment_url'] = instance.attachment.url

        return ret


class CustomerHotelMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.get_full_name', read_only=True)
    receiver_name = serializers.CharField(source='receiver.get_full_name', read_only=True)

    class Meta:
        model = CustomerHotelMessage
        fields = ['id', 'booking', 'sender', 'sender_name', 'receiver', 'receiver_name', 'message', 'is_read', 'created_at']
        read_only_fields = ['id', 'sender', 'created_at']


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    admin_user = serializers.CharField(source='user.username', read_only=True)
    target_model = serializers.CharField(source='entity_type', read_only=True)
    target_id = serializers.CharField(source='entity_id', read_only=True)
    timestamp = serializers.DateTimeField(source='created_at', read_only=True)
    previous_state = serializers.JSONField(source='old_values', read_only=True)
    new_state = serializers.JSONField(source='new_values', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'user_name', 'admin_user', 'action',
            'entity_type', 'target_model', 'entity_id', 'target_id',
            'old_values', 'previous_state', 'new_values', 'new_state',
            'ip_address', 'created_at', 'timestamp'
        ]
        read_only_fields = fields


class PaymentOrderCreateSerializer(serializers.Serializer):
    booking_id = serializers.CharField(required=True)
    # Optional client-side fields for frontend compatibility; strictly calculated and validated server-side
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PaymentVerifySerializer(serializers.Serializer):
    booking_id = serializers.CharField(required=True)
    razorpay_order_id = serializers.CharField(required=True)
    razorpay_payment_id = serializers.CharField(required=True)
    razorpay_signature = serializers.CharField(required=True)


class PaymentRetrySerializer(serializers.Serializer):
    booking_id = serializers.CharField(required=True)


class RefundCreateSerializer(serializers.Serializer):
    booking_id = serializers.CharField(required=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    reason = serializers.CharField(required=False, default="Hotel Owner / Platform approved cancellation refund")
    idempotency_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    refund_mode = serializers.ChoiceField(
        choices=[Refund.REFUND_MODE_ORIGINAL, Refund.REFUND_MODE_BANK, Refund.REFUND_MODE_UPI],
        default=Refund.REFUND_MODE_ORIGINAL,
        required=False
    )
    account_holder_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    account_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    ifsc_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    upi_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    admin_notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class CustomerPayoutRequestSerializer(serializers.Serializer):
    PAYOUT_MODE_CHOICES = (
        ('NEFT', 'National Electronic Funds Transfer (NEFT)'),
        ('IMPS', 'Immediate Payment Service (IMPS)'),
        ('RTGS', 'Real Time Gross Settlement (RTGS)'),
        ('UPI', 'Unified Payments Interface (UPI)'),
    )

    booking_id = serializers.CharField(required=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    payout_mode = serializers.ChoiceField(choices=PAYOUT_MODE_CHOICES, default='NEFT', required=False)
    
    account_holder_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    account_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    ifsc_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    upi_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    idempotency_key = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    narration = serializers.CharField(required=False, allow_blank=True, default="Customer Refund")
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        mode = attrs.get('payout_mode', 'NEFT').upper()
        from util.validators import validate_indian_bank_account, validate_indian_ifsc, validate_indian_upi

        if mode == 'UPI':
            upi_id = attrs.get('upi_id')
            if not upi_id:
                raise serializers.ValidationError({"upi_id": "UPI ID (VPA) is required when payout_mode is 'UPI'."})
            try:
                attrs['upi_id'] = validate_indian_upi(upi_id)
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"upi_id": e.detail})
        else:
            acc_num = attrs.get('account_number')
            ifsc = attrs.get('ifsc_code')
            if not acc_num:
                raise serializers.ValidationError({"account_number": f"Account number is required when payout_mode is '{mode}'."})
            if not ifsc:
                raise serializers.ValidationError({"ifsc_code": f"IFSC code is required when payout_mode is '{mode}'."})
            try:
                attrs['account_number'] = validate_indian_bank_account(acc_num)
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"account_number": e.detail})
            try:
                attrs['ifsc_code'] = validate_indian_ifsc(ifsc)
            except serializers.ValidationError as e:
                raise serializers.ValidationError({"ifsc_code": e.detail})

        return attrs

import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class Department(models.Model):
    CODE_RESERVATION = 'RESERVATION'
    CODE_CUSTOMER_SUPPORT = 'CUSTOMER_SUPPORT'
    CODE_REFUNDS_AND_CLAIMS = 'REFUNDS_AND_CLAIMS'
    CODE_PAYOUT_AND_ESCROW = 'PAYOUT_AND_ESCROW'
    CODE_HOTEL_VERIFICATION = 'HOTEL_VERIFICATION'

    # Backward compatibility aliases
    CODE_REFUND = 'REFUNDS_AND_CLAIMS'
    CODE_PAYOUT = 'PAYOUT_AND_ESCROW'

    DEPARTMENT_CHOICES = (
        (CODE_RESERVATION, 'Reservation'),
        (CODE_CUSTOMER_SUPPORT, 'Customer Support'),
        (CODE_REFUNDS_AND_CLAIMS, 'Refunds & Claims'),
        (CODE_PAYOUT_AND_ESCROW, 'Payout & Escrow'),
        (CODE_HOTEL_VERIFICATION, 'Hotel Verification'),
    )

    @classmethod
    def normalize_code(cls, code_str):
        if not code_str:
            return ""
        c = str(code_str).strip().upper()
        if c in ['REFUND', 'REFUNDS', 'REFUNDS_AND_CLAIMS', 'CLAIMS']:
            return cls.CODE_REFUNDS_AND_CLAIMS
        if c in ['PAYOUT', 'PAYOUTS', 'PAYOUT_AND_ESCROW', 'ESCROW']:
            return cls.CODE_PAYOUT_AND_ESCROW
        if c in ['SUPPORT', 'CUSTOMER_SUPPORT', 'CS']:
            return cls.CODE_CUSTOMER_SUPPORT
        if c in ['HOTEL', 'HOTEL_VERIFICATION', 'VERIFICATION']:
            return cls.CODE_HOTEL_VERIFICATION
        if c in ['RESERVATION', 'RESERVATIONS', 'BOOKING', 'BOOKINGS']:
            return cls.CODE_RESERVATION
        return c

    code = models.CharField(max_length=50, unique=True, choices=DEPARTMENT_CHOICES, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class StaffPermission(models.Model):
    ACTION_VIEW = 'VIEW'
    ACTION_CREATE = 'CREATE'
    ACTION_EDIT = 'EDIT'
    ACTION_APPROVE = 'APPROVE'
    ACTION_REJECT = 'REJECT'
    ACTION_PROCESS_REFUND = 'PROCESS_REFUND'
    ACTION_PROCESS_PAYOUT = 'PROCESS_PAYOUT'
    ACTION_MANAGE_SUPPORT = 'MANAGE_SUPPORT'
    ACTION_VERIFY_HOTEL = 'VERIFY_HOTEL'

    ACTION_CHOICES = (
        (ACTION_VIEW, 'View'),
        (ACTION_CREATE, 'Create'),
        (ACTION_EDIT, 'Edit'),
        (ACTION_APPROVE, 'Approve'),
        (ACTION_REJECT, 'Reject'),
        (ACTION_PROCESS_REFUND, 'Process Refund'),
        (ACTION_PROCESS_PAYOUT, 'Process Payout'),
        (ACTION_MANAGE_SUPPORT, 'Manage Support'),
        (ACTION_VERIFY_HOTEL, 'Verify Hotel'),
    )

    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='permissions', null=True, blank=True)
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, default=ACTION_VIEW)
    description = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.name} [{self.code}]"


class StaffProfile(models.Model):
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_INACTIVE = 'INACTIVE'
    STATUS_SUSPENDED = 'SUSPENDED'

    STATUS_CHOICES = (
        (STATUS_ACTIVE, 'Active'),
        (STATUS_INACTIVE, 'Inactive'),
        (STATUS_SUSPENDED, 'Suspended'),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_profile')
    employee_id = models.CharField(max_length=50, unique=True, db_index=True)
    login_id = models.CharField(max_length=50, unique=True, db_index=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='staff_members')
    permissions = models.ManyToManyField(StaffPermission, blank=True, related_name='staff_profiles')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    must_change_password = models.BooleanField(default=True)
    designation = models.CharField(max_length=100, blank=True, default='')
    phone_number = models.CharField(max_length=20, blank=True, default='')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_staff_profiles')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['employee_id']

    def __str__(self):
        return f"{self.employee_id} - {self.login_id} ({self.department.name})"

    @property
    def is_active_account(self):
        return self.status == self.STATUS_ACTIVE and self.user.is_active and not getattr(self.user, 'is_blocked', False)

    def has_perm(self, perm_code):
        if not self.is_active_account:
            return False
        if not perm_code:
            return True
        target = str(perm_code).strip().upper()
        assigned_perms = list(self.permissions.values_list('code', flat=True))
        if assigned_perms:
            if target in assigned_perms or '*' in assigned_perms:
                return True
            return self._matches_permission_alias(assigned_perms, target)
        else:
            # Default to all permissions configured for employee's assigned department
            if self.department:
                dept_perms = list(self.department.permissions.values_list('code', flat=True))
                if target in dept_perms:
                    return True
                return self._matches_permission_alias(dept_perms, target)
            return False

    @staticmethod
    def _matches_permission_alias(perm_set, target):
        aliases = {
            # Reservation
            'VIEW_BOOKINGS': {'VIEW_BOOKINGS', 'MANAGE_RESERVATIONS'},
            'MANAGE_RESERVATIONS': {'MANAGE_RESERVATIONS', 'EDIT_BOOKINGS', 'CREATE_BOOKINGS', 'ALLOCATE_ROOMS', 'CHECKIN_GUEST', 'CHECKOUT_GUEST'},
            'CHECKIN_GUEST': {'CHECKIN_GUEST', 'MANAGE_RESERVATIONS', 'EDIT_BOOKINGS'},
            'CHECKOUT_GUEST': {'CHECKOUT_GUEST', 'MANAGE_RESERVATIONS', 'EDIT_BOOKINGS'},
            'ALLOCATE_ROOMS': {'ALLOCATE_ROOMS', 'MANAGE_RESERVATIONS', 'EDIT_BOOKINGS'},
            # Customer Support
            'VIEW_TICKETS': {'VIEW_TICKETS', 'VIEW_SUPPORT', 'MANAGE_SUPPORT'},
            'VIEW_SUPPORT': {'VIEW_SUPPORT', 'VIEW_TICKETS', 'MANAGE_SUPPORT'},
            'MANAGE_SUPPORT': {'MANAGE_SUPPORT', 'RESPOND_TICKET', 'ADD_INTERNAL_NOTE', 'ESCALATE_TICKET', 'EDIT_SUPPORT'},
            'RESPOND_TICKET': {'RESPOND_TICKET', 'MANAGE_SUPPORT', 'EDIT_SUPPORT'},
            'ADD_INTERNAL_NOTE': {'ADD_INTERNAL_NOTE', 'MANAGE_SUPPORT', 'EDIT_SUPPORT'},
            'ESCALATE_TICKET': {'ESCALATE_TICKET', 'MANAGE_SUPPORT', 'EDIT_SUPPORT'},
            # Refunds & Claims
            'VIEW_REFUNDS': {'VIEW_REFUNDS', 'VERIFY_CLAIM', 'AUDIT_REFUND', 'PROCESS_REFUND', 'APPROVE_REFUND'},
            'VERIFY_CLAIM': {'VERIFY_CLAIM', 'VIEW_REFUNDS', 'APPROVE_REFUND'},
            'AUDIT_REFUND': {'AUDIT_REFUND', 'VIEW_REFUNDS'},
            'PROCESS_REFUND': {'PROCESS_REFUND', 'APPROVE_REFUND'},
            'APPROVE_REFUND': {'APPROVE_REFUND', 'PROCESS_REFUND'},
            'REJECT_REFUND': {'REJECT_REFUND', 'PROCESS_REFUND'},
            # Payout & Escrow
            'VIEW_PAYOUTS': {'VIEW_PAYOUTS', 'MANAGE_ESCROW', 'AUDIT_SETTLEMENT', 'PROCESS_PAYOUT', 'APPROVE_PAYOUT'},
            'MANAGE_ESCROW': {'MANAGE_ESCROW', 'VIEW_PAYOUTS', 'AUDIT_SETTLEMENT'},
            'AUDIT_SETTLEMENT': {'AUDIT_SETTLEMENT', 'VIEW_PAYOUTS', 'MANAGE_ESCROW'},
            'PROCESS_PAYOUT': {'PROCESS_PAYOUT', 'APPROVE_PAYOUT'},
            'APPROVE_PAYOUT': {'APPROVE_PAYOUT', 'PROCESS_PAYOUT'},
            'REJECT_PAYOUT': {'REJECT_PAYOUT', 'PROCESS_PAYOUT'},
            # Hotel Verification
            'VIEW_HOTELS': {'VIEW_HOTELS', 'VERIFY_HOTEL', 'VERIFY_HOTELS', 'REVIEW_DOCUMENTS', 'APPROVE_HOTEL'},
            'REVIEW_DOCUMENTS': {'REVIEW_DOCUMENTS', 'VIEW_HOTELS', 'VERIFY_HOTEL', 'VERIFY_HOTELS'},
            'VERIFY_HOTEL': {'VERIFY_HOTEL', 'VERIFY_HOTELS', 'APPROVE_HOTEL', 'REJECT_HOTEL'},
            'VERIFY_HOTELS': {'VERIFY_HOTELS', 'VERIFY_HOTEL', 'APPROVE_HOTEL', 'REJECT_HOTEL'},
            'APPROVE_HOTEL': {'APPROVE_HOTEL', 'VERIFY_HOTEL', 'VERIFY_HOTELS'},
            'REJECT_HOTEL': {'REJECT_HOTEL', 'VERIFY_HOTEL', 'VERIFY_HOTELS'},
        }
        allowed_sources = aliases.get(target, {target})
        return bool(set(perm_set).intersection(allowed_sources))


class StaffPasswordResetToken(models.Model):
    staff_profile = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token_hash = models.CharField(max_length=128, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at


class StaffTicketNote(models.Model):
    ticket = models.ForeignKey('payments.SupportTicket', on_delete=models.CASCADE, related_name='staff_notes')
    staff = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='ticket_notes')
    note = models.TextField()
    is_internal_only = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Note on {self.ticket.ticket_number} by {self.staff}"


class StaffNotification(models.Model):
    recipient = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, null=True, blank=True, related_name='staff_notifications')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True, related_name='department_notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, default='GENERAL')
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.notification_type}] {self.title}"


class StaffActivityLog(models.Model):
    staff = models.ForeignKey(StaffProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    employee_id = models.CharField(max_length=50, db_index=True)
    actor_username = models.CharField(max_length=150)
    action = models.CharField(max_length=100, db_index=True)
    target_entity_type = models.CharField(max_length=100, blank=True, default='')
    target_entity_id = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.timestamp} - {self.employee_id} - {self.action}"


class StaffAssignment(models.Model):
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name='assignments')
    entity_type = models.CharField(max_length=50, db_index=True)
    entity_id = models.CharField(max_length=100, db_index=True)
    notes = models.TextField(blank=True, default='')
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-assigned_at']

    def __str__(self):
        return f"{self.staff.employee_id} -> {self.entity_type} #{self.entity_id}"

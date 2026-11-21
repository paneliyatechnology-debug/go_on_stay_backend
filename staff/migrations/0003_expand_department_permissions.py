from django.db import migrations


def seed_expanded_permissions(apps, schema_editor):
    Department = apps.get_model('staff', 'Department')
    StaffPermission = apps.get_model('staff', 'StaffPermission')

    dept_objs = {d.code: d for d in Department.objects.all()}

    new_permissions = [
        # Reservation
        {'code': 'MANAGE_RESERVATIONS', 'name': 'Manage Reservations', 'dept': 'RESERVATION', 'action': 'EDIT', 'desc': 'Allows managing bookings, stay modifications, and check-ins.'},
        {'code': 'ALLOCATE_ROOMS', 'name': 'Allocate Rooms', 'dept': 'RESERVATION', 'action': 'EDIT', 'desc': 'Allows assigning room numbers and handling room upgrades.'},
        {'code': 'CHECKIN_GUEST', 'name': 'Check-In Guest', 'dept': 'RESERVATION', 'action': 'EDIT', 'desc': 'Allows processing guest arrival check-in.'},
        {'code': 'CHECKOUT_GUEST', 'name': 'Check-Out Guest', 'dept': 'RESERVATION', 'action': 'EDIT', 'desc': 'Allows processing guest departure check-out.'},

        # Customer Support
        {'code': 'VIEW_TICKETS', 'name': 'View Support Tickets', 'dept': 'CUSTOMER_SUPPORT', 'action': 'VIEW', 'desc': 'Allows viewing support tickets, user inquiries, and history.'},
        {'code': 'RESPOND_TICKET', 'name': 'Respond to Support Ticket', 'dept': 'CUSTOMER_SUPPORT', 'action': 'MANAGE_SUPPORT', 'desc': 'Allows replying to customer messages and resolving inquiries.'},
        {'code': 'ADD_INTERNAL_NOTE', 'name': 'Add Internal Staff Notes', 'dept': 'CUSTOMER_SUPPORT', 'action': 'MANAGE_SUPPORT', 'desc': 'Allows adding internal staff notes to support tickets.'},
        {'code': 'ESCALATE_TICKET', 'name': 'Escalate Support Ticket', 'dept': 'CUSTOMER_SUPPORT', 'action': 'MANAGE_SUPPORT', 'desc': 'Allows escalating unresolved tickets to supervisors.'},

        # Refunds & Claims
        {'code': 'VERIFY_CLAIM', 'name': 'Verify Refund Claim', 'dept': 'REFUNDS_AND_CLAIMS', 'action': 'VIEW', 'desc': 'Allows verifying booking cancellation policy eligibility.'},
        {'code': 'AUDIT_REFUND', 'name': 'Audit Refund Records', 'dept': 'REFUNDS_AND_CLAIMS', 'action': 'VIEW', 'desc': 'Allows auditing refund logs and gateway transaction history.'},

        # Payout & Escrow
        {'code': 'MANAGE_ESCROW', 'name': 'Manage Escrow Ledger', 'dept': 'PAYOUT_AND_ESCROW', 'action': 'VIEW', 'desc': 'Allows inspecting on-hold earnings and 7-day maturity statuses.'},
        {'code': 'AUDIT_SETTLEMENT', 'name': 'Audit Settlement Statements', 'dept': 'PAYOUT_AND_ESCROW', 'action': 'VIEW', 'desc': 'Allows auditing host payout statements and platform fees.'},

        # Hotel Verification
        {'code': 'REVIEW_DOCUMENTS', 'name': 'Review Verification Documents', 'dept': 'HOTEL_VERIFICATION', 'action': 'VIEW', 'desc': 'Allows inspecting hotel business licenses and registration certificates.'},
    ]

    for p in new_permissions:
        dept = dept_objs.get(p['dept'])
        if dept:
            StaffPermission.objects.get_or_create(
                code=p['code'],
                defaults={
                    'name': p['name'],
                    'department': dept,
                    'action': p['action'],
                    'description': p['desc']
                }
            )


def reverse_expanded_permissions(apps, schema_editor):
    StaffPermission = apps.get_model('staff', 'StaffPermission')
    codes_to_remove = [
        'MANAGE_RESERVATIONS', 'ALLOCATE_ROOMS', 'CHECKIN_GUEST', 'CHECKOUT_GUEST',
        'VIEW_TICKETS', 'RESPOND_TICKET', 'ADD_INTERNAL_NOTE', 'ESCALATE_TICKET',
        'VERIFY_CLAIM', 'AUDIT_REFUND',
        'MANAGE_ESCROW', 'AUDIT_SETTLEMENT',
        'REVIEW_DOCUMENTS'
    ]
    StaffPermission.objects.filter(code__in=codes_to_remove).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0002_seed_departments_and_permissions'),
    ]

    operations = [
        migrations.RunPython(seed_expanded_permissions, reverse_expanded_permissions),
    ]

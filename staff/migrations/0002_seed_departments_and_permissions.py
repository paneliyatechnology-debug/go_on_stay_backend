from django.db import migrations


def seed_departments_and_permissions(apps, schema_editor):
    Department = apps.get_model('staff', 'Department')
    StaffPermission = apps.get_model('staff', 'StaffPermission')

    departments_data = [
        {
            'code': 'RESERVATION',
            'name': 'Reservation',
            'description': 'Handles room reservations, booking lookups, guest communications, and check-in/out inquiries.',
        },
        {
            'code': 'CUSTOMER_SUPPORT',
            'name': 'Customer Support',
            'description': 'Handles guest support tickets, inquiries, internal coordination notes, and complaint resolution.',
        },
        {
            'code': 'REFUNDS_AND_CLAIMS',
            'name': 'Refunds & Claims',
            'description': 'Reviews cancellation refund eligibility and executes secure payment gateway refund transactions.',
        },
        {
            'code': 'PAYOUT_AND_ESCROW',
            'name': 'Payout & Escrow',
            'description': 'Manages host payouts, verifies 7-day holding maturity rules, and processes partner disbursements.',
        },
        {
            'code': 'HOTEL_VERIFICATION',
            'name': 'Hotel Verification',
            'description': 'Audits newly registered hotel properties, reviews business documents, and conducts compliance checks.',
        },
    ]

    dept_objs = {}
    for d in departments_data:
        dept, _ = Department.objects.get_or_create(
            code=d['code'],
            defaults={'name': d['name'], 'description': d['description'], 'is_active': True}
        )
        dept_objs[d['code']] = dept

    dept_objs['REFUND'] = dept_objs.get('REFUNDS_AND_CLAIMS')
    dept_objs['PAYOUT'] = dept_objs.get('PAYOUT_AND_ESCROW')

    permissions_data = [
        # Reservation
        {'code': 'VIEW_BOOKINGS', 'name': 'View Bookings', 'dept': 'RESERVATION', 'action': 'VIEW', 'desc': 'Allows viewing guest bookings and reservation details.'},
        {'code': 'CREATE_BOOKINGS', 'name': 'Create Bookings', 'dept': 'RESERVATION', 'action': 'CREATE', 'desc': 'Allows creating offline or assisted guest bookings.'},
        {'code': 'EDIT_BOOKINGS', 'name': 'Edit Bookings', 'dept': 'RESERVATION', 'action': 'EDIT', 'desc': 'Allows updating booking notes and stay dates.'},

        # Customer Support
        {'code': 'VIEW_SUPPORT', 'name': 'View Support Tickets', 'dept': 'CUSTOMER_SUPPORT', 'action': 'VIEW', 'desc': 'Allows viewing customer support tickets and history.'},
        {'code': 'MANAGE_SUPPORT', 'name': 'Manage Support Tickets', 'dept': 'CUSTOMER_SUPPORT', 'action': 'MANAGE_SUPPORT', 'desc': 'Allows replying to tickets, changing ticket status, and adding internal notes.'},
        {'code': 'EDIT_SUPPORT', 'name': 'Edit Support Tickets', 'dept': 'CUSTOMER_SUPPORT', 'action': 'EDIT', 'desc': 'Allows updating ticket metadata and priority.'},

        # Refund
        {'code': 'VIEW_REFUNDS', 'name': 'View Refunds', 'dept': 'REFUND', 'action': 'VIEW', 'desc': 'Allows viewing refund requests and transaction logs.'},
        {'code': 'PROCESS_REFUND', 'name': 'Process Refunds', 'dept': 'REFUND', 'action': 'PROCESS_REFUND', 'desc': 'Allows executing live refund disbursements through Razorpay gateway.'},
        {'code': 'APPROVE_REFUND', 'name': 'Approve Refund Request', 'dept': 'REFUND', 'action': 'APPROVE', 'desc': 'Allows approving pending refund claims.'},
        {'code': 'REJECT_REFUND', 'name': 'Reject Refund Request', 'dept': 'REFUND', 'action': 'REJECT', 'desc': 'Allows rejecting ineligible refund claims.'},

        # Payout
        {'code': 'VIEW_PAYOUTS', 'name': 'View Payouts', 'dept': 'PAYOUT', 'action': 'VIEW', 'desc': 'Allows viewing host payouts and earning balances.'},
        {'code': 'PROCESS_PAYOUT', 'name': 'Process Payouts', 'dept': 'PAYOUT', 'action': 'PROCESS_PAYOUT', 'desc': 'Allows executing host payout disbursements after 7-day maturity check.'},
        {'code': 'APPROVE_PAYOUT', 'name': 'Approve Host Payout', 'dept': 'PAYOUT', 'action': 'APPROVE', 'desc': 'Allows approving host payout requests.'},
        {'code': 'REJECT_PAYOUT', 'name': 'Reject Host Payout', 'dept': 'PAYOUT', 'action': 'REJECT', 'desc': 'Allows rejecting host payout requests.'},

        # Hotel Verification
        {'code': 'VIEW_HOTELS', 'name': 'View Hotel Applications', 'dept': 'HOTEL_VERIFICATION', 'action': 'VIEW', 'desc': 'Allows viewing submitted hotel listings and verification documents.'},
        {'code': 'VERIFY_HOTEL', 'name': 'Verify Hotel Listings', 'dept': 'HOTEL_VERIFICATION', 'action': 'VERIFY_HOTEL', 'desc': 'Allows approving or rejecting hotel onboarding applications.'},
        {'code': 'APPROVE_HOTEL', 'name': 'Approve Hotel', 'dept': 'HOTEL_VERIFICATION', 'action': 'APPROVE', 'desc': 'Allows approving verified hotels.'},
        {'code': 'REJECT_HOTEL', 'name': 'Reject Hotel', 'dept': 'HOTEL_VERIFICATION', 'action': 'REJECT', 'desc': 'Allows rejecting hotel applications with a mandatory reason.'},
    ]

    for p in permissions_data:
        StaffPermission.objects.get_or_create(
            code=p['code'],
            defaults={
                'name': p['name'],
                'department': dept_objs.get(p['dept']),
                'action': p['action'],
                'description': p['desc'],
            }
        )


def reverse_seed(apps, schema_editor):
    Department = apps.get_model('staff', 'Department')
    StaffPermission = apps.get_model('staff', 'StaffPermission')
    StaffPermission.objects.all().delete()
    Department.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_departments_and_permissions, reverse_seed),
    ]

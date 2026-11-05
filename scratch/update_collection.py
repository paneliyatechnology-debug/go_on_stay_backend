import json

path = 'BookMyRoom_Master_Backend.postman_collection.json'
with open(path, 'r', encoding='utf-8') as f:
    col = json.load(f)

# Find Payments Folder
payments_folder = None
for it in col['item']:
    if '06. Payments' in it['name']:
        payments_folder = it
        break

refund_folder = {
    'name': 'Refunds & Cancellation Settlements (Razorpay & RazorpayX)',
    'item': [
        {
            'name': '1. Admin: Process Refund (Original Source - Razorpay)',
            'request': {
                'method': 'POST',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{admin_token}}'},
                    {'key': 'Content-Type', 'value': 'application/json'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/refund/process/',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'refund', 'process', '']
                },
                'body': {
                    'mode': 'raw',
                    'raw': json.dumps({
                        'booking_id': '{{booking_id}}',
                        'refund_mode': 'ORIGINAL_SOURCE',
                        'reason': 'Hotel Owner / Platform approved cancellation refund',
                        'idempotency_key': 'ref_{{booking_id}}'
                    }, indent=2)
                }
            }
        },
        {
            'name': '2. Admin: Process Refund (Bank Transfer - RazorpayX Payout)',
            'request': {
                'method': 'POST',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{admin_token}}'},
                    {'key': 'Content-Type', 'value': 'application/json'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/refund/process/',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'refund', 'process', '']
                },
                'body': {
                    'mode': 'raw',
                    'raw': json.dumps({
                        'booking_id': '{{booking_id}}',
                        'refund_mode': 'BANK_TRANSFER',
                        'account_holder_name': 'Rajesh Sharma',
                        'bank_name': 'HDFC Bank',
                        'account_number': '123456789012',
                        'ifsc_code': 'HDFC0001234',
                        'reason': 'Approved guest cancellation direct bank refund'
                    }, indent=2)
                }
            }
        },
        {
            'name': '3. Admin: Process Refund (UPI - RazorpayX Payout)',
            'request': {
                'method': 'POST',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{admin_token}}'},
                    {'key': 'Content-Type', 'value': 'application/json'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/refund/process/',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'refund', 'process', '']
                },
                'body': {
                    'mode': 'raw',
                    'raw': json.dumps({
                        'booking_id': '{{booking_id}}',
                        'refund_mode': 'UPI',
                        'account_holder_name': 'Rajesh Sharma',
                        'upi_id': 'rajesh@okhdfcbank',
                        'reason': 'Approved guest cancellation direct UPI refund'
                    }, indent=2)
                }
            }
        },
        {
            'name': '4. Get Refund Details (By Booking ID or Refund ID)',
            'request': {
                'method': 'GET',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{admin_token}}'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/refunds/{{booking_id}}/',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'refunds', '{{booking_id}}', '']
                }
            }
        },
        {
            'name': '5. Check Refund Status (with Live Gateway Sync)',
            'request': {
                'method': 'GET',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{admin_token}}'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/refunds/{{booking_id}}/status/?sync=true',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'refunds', '{{booking_id}}', 'status', ''],
                    'query': [{'key': 'sync', 'value': 'true'}]
                }
            }
        },
        {
            'name': '6. Retry Failed Refund (Safe Idempotent Retry)',
            'request': {
                'method': 'POST',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{admin_token}}'},
                    {'key': 'Content-Type', 'value': 'application/json'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/refunds/{{booking_id}}/retry/',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'refunds', '{{booking_id}}', 'retry', '']
                },
                'body': {
                    'mode': 'raw',
                    'raw': '{\n  \"notes\": \"Retrying failed refund after gateway clearance\"\n}'
                }
            }
        },
        {
            'name': '7. Admin: Filtered Refunds Listing',
            'request': {
                'method': 'GET',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{admin_token}}'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/admin/refunds/?status=REFUNDED&refund_mode=BANK_TRANSFER',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'admin', 'refunds', ''],
                    'query': [
                        {'key': 'status', 'value': 'REFUNDED'},
                        {'key': 'refund_mode', 'value': 'BANK_TRANSFER'}
                    ]
                }
            }
        }
    ]
}

existing_rf = [i for i, x in enumerate(payments_folder['item']) if 'Refunds' in x['name']]
if existing_rf:
    payments_folder['item'][existing_rf[0]] = refund_folder
else:
    payments_folder['item'].append(refund_folder)

# Also update Bookings Management -> Cancel Booking with bank & upi details sample
bookings_folder = None
for it in col['item']:
    if '05. Bookings' in it['name']:
        bookings_folder = it
        break

if bookings_folder:
    cancel_item = None
    for it in bookings_folder['item']:
        if 'Cancel' in it['name']:
            it['body'] = {
                'mode': 'raw',
                'raw': json.dumps({
                    'reason': 'Change of travel plans',
                    'refund_mode': 'BANK_TRANSFER',
                    'account_holder_name': 'Rajesh Sharma',
                    'bank_name': 'HDFC Bank',
                    'account_number': '123456789012',
                    'ifsc_code': 'HDFC0001234',
                    'upi_id': 'rajesh@okhdfcbank'
                }, indent=2)
            }
            break

with open(path, 'w', encoding='utf-8') as f:
    json.dump(col, f, indent=2, ensure_ascii=False)

print('Postman collection successfully updated with complete Refund System endpoints!')


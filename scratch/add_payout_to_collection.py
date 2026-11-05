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

payout_subfolder = {
    'name': 'RazorpayX Customer Bank Payout API (Test Mode Sandbox)',
    'item': [
        {
            'name': '1. Customer Payout: Bank Transfer (NEFT / IMPS / RTGS)',
            'request': {
                'method': 'POST',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{admin_token}}'},
                    {'key': 'Content-Type', 'value': 'application/json'},
                    {'key': 'X-Payout-Idempotency', 'value': 'idem_pout_{{$timestamp}}'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/payouts/customer/',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'payouts', 'customer', '']
                },
                'body': {
                    'mode': 'raw',
                    'raw': json.dumps({
                        'booking_id': '{{booking_id}}',
                        'amount': 2500.00,
                        'payout_mode': 'NEFT',
                        'account_holder_name': 'Rajesh Sharma',
                        'bank_name': 'HDFC Bank',
                        'account_number': '123456789012',
                        'ifsc_code': 'HDFC0001234',
                        'narration': 'Customer Stay Refund',
                        'idempotency_key': 'pout_idem_{{$timestamp}}'
                    }, indent=2)
                }
            }
        },
        {
            'name': '2. Customer Payout: UPI VPA Transfer',
            'request': {
                'method': 'POST',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{admin_token}}'},
                    {'key': 'Content-Type', 'value': 'application/json'},
                    {'key': 'X-Payout-Idempotency', 'value': 'idem_pout_upi_{{$timestamp}}'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/payouts/customer/',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'payouts', 'customer', '']
                },
                'body': {
                    'mode': 'raw',
                    'raw': json.dumps({
                        'booking_id': '{{booking_id}}',
                        'amount': 2500.00,
                        'payout_mode': 'UPI',
                        'account_holder_name': 'Rajesh Sharma',
                        'upi_id': 'rajesh@okhdfcbank',
                        'narration': 'Customer UPI Refund',
                        'idempotency_key': 'pout_idem_upi_{{$timestamp}}'
                    }, indent=2)
                }
            }
        },
        {
            'name': '3. Customer Payout: Fetch Details & Gateway Sync',
            'request': {
                'method': 'GET',
                'header': [
                    {'key': 'Authorization', 'value': 'Bearer {{admin_token}}'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/payouts/customer/{{booking_id}}/?sync=true',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'payouts', 'customer', '{{booking_id}}', ''],
                    'query': [{'key': 'sync', 'value': 'true'}]
                }
            }
        },
        {
            'name': '4. RazorpayX Payout Webhook Simulation (payout.processed)',
            'request': {
                'method': 'POST',
                'header': [
                    {'key': 'Content-Type', 'value': 'application/json'},
                    {'key': 'X-Razorpay-Signature', 'value': '{{razorpay_webhook_signature}}'}
                ],
                'url': {
                    'raw': '{{base_url}}/api/payments/webhook/',
                    'host': ['{{base_url}}'],
                    'path': ['api', 'payments', 'webhook', '']
                },
                'body': {
                    'mode': 'raw',
                    'raw': json.dumps({
                        'entity': 'event',
                        'account_id': 'acc_test_123',
                        'event': 'payout.processed',
                        'contains': ['payout'],
                        'payload': {
                            'payout': {
                                'entity': {
                                    'id': 'pout_test_example123',
                                    'entity': 'payout',
                                    'amount': 250000,
                                    'currency': 'INR',
                                    'status': 'processed',
                                    'purpose': 'refund',
                                    'utr': 'HDFCN9876543210',
                                    'mode': 'NEFT',
                                    'reference_id': 'pout_BK-123456_ref'
                                }
                            }
                        }
                    }, indent=2)
                }
            }
        }
    ]
}

# Replace or append subfolder
existing_idx = [i for i, x in enumerate(payments_folder['item']) if 'Customer Bank Payout' in x['name']]
if existing_idx:
    payments_folder['item'][existing_idx[0]] = payout_subfolder
else:
    payments_folder['item'].append(payout_subfolder)

with open(path, 'w', encoding='utf-8') as f:
    json.dump(col, f, indent=2, ensure_ascii=False)

print('Postman collection successfully updated with RazorpayX Customer Bank Payout API!')


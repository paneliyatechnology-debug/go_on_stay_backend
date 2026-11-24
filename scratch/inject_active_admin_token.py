"""
Generate fresh active Admin JWT tokens and set them as default collection variables,
then push update to Postman Cloud.
"""

import os
import sys
import json
import ssl
import urllib.request

sys.path.insert(0, os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from users.models import User
from rest_framework_simplejwt.tokens import RefreshToken

def main():
    admin_user = User.objects.filter(email='admin@bookmyroom.com').first()
    if not admin_user:
        admin_user = User.objects.filter(role='ADMIN').first()
    
    refresh = RefreshToken.for_user(admin_user)
    access_token = str(refresh.access_token)
    refresh_token = str(refresh)
    print(f"Generated fresh Admin JWT token for {admin_user.email}")

    # Load master collection
    target = "GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json"
    with open(target, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. Update Collection Variables with active token
    var_dict = {v['key']: v for v in data.get('variable', [])}
    
    updates = {
        'base_url': 'http://127.0.0.1:8000',
        'baseUrl': 'http://127.0.0.1:8000',
        'admin_token': access_token,
        'admin_access_token': access_token,
        'token': access_token,
        'access_token': access_token,
        'admin_refresh': refresh_token,
    }

    for k, v in updates.items():
        if k in var_dict:
            var_dict[k]['value'] = v
        else:
            data.setdefault('variable', []).append({'key': k, 'value': v, 'type': 'string'})

    # 2. Also ensure all request headers in Folder 16 use Bearer {{admin_token}} or {{admin_access_token}}
    for folder in data.get('item', []):
        if '16.' in folder.get('name', ''):
            for sub in folder.get('item', []):
                for req_item in sub.get('item', []):
                    req = req_item.get('request', {})
                    for h in req.get('header', []):
                        if h.get('key') == 'Authorization' and 'Bearer' in h.get('value', ''):
                            # Default to {{admin_token}} so it works universally
                            val = h.get('value')
                            if 'admin' in val:
                                h['value'] = 'Bearer {{admin_token}}'

    # Save to files
    with open(target, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    with open("postman_collections/01_GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    # Also update standalone
    if os.path.exists("GOONSTAY_4_LEVEL_ADMIN_STAFF_HIERARCHY_POSTMAN.json"):
        with open("GOONSTAY_4_LEVEL_ADMIN_STAFF_HIERARCHY_POSTMAN.json", 'r', encoding='utf-8') as f:
            stand = json.load(f)
        stand['variable'] = [
            {'key': 'base_url', 'value': 'http://127.0.0.1:8000', 'type': 'string'},
            {'key': 'admin_token', 'value': access_token, 'type': 'string'},
            {'key': 'admin_access_token', 'value': access_token, 'type': 'string'},
            {'key': 'access_token', 'value': access_token, 'type': 'string'},
            {'key': 'token', 'value': access_token, 'type': 'string'}
        ]
        with open("GOONSTAY_4_LEVEL_ADMIN_STAFF_HIERARCHY_POSTMAN.json", 'w', encoding='utf-8') as f:
            json.dump(stand, f, indent=2)

    # 3. Push to Postman Cloud API
    env_vars = {}
    with open('.env', 'r', encoding='utf-8') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.strip().split('=', 1)
                env_vars[k.strip()] = v.strip()

    api_key = env_vars.get('POSTMAN_API_KEY')
    collection_uid = env_vars.get('POSTMAN_COLLECTION_UID')

    if api_key and collection_uid:
        url = f"https://api.getpostman.com/collections/{collection_uid}"
        payload = {
            "collection": {
                "info": data.get("info", {}),
                "item": data.get("item", []),
                "variable": data.get("variable", [])
            }
        }
        req_data = json.dumps(payload).encode('utf-8')
        headers = {
            "X-Api-Key": api_key,
            "Content-Type": "application/json"
        }
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, data=req_data, headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                print("Cloud Sync SUCCESS: Pre-filled active Admin token directly in Postman Collection!")
        except Exception as e:
            print(f"Cloud sync error: {e}")

if __name__ == "__main__":
    main()

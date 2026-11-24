"""
Ensure collection variables include base_url, admin_access_token, token,
and Admin Login script sets both admin_token and admin_access_token.
Then push update to Postman Cloud API.
"""

import json
import os
import urllib.request
import ssl

def main():
    target = "GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json"
    with open(target, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. Update Collection Variables
    existing_vars = {v['key']: v for v in data.get('variable', [])}
    
    needed_vars = [
        {'key': 'base_url', 'value': 'http://127.0.0.1:8000', 'type': 'string'},
        {'key': 'baseUrl', 'value': 'http://127.0.0.1:8000', 'type': 'string'},
        {'key': 'admin_token', 'value': '', 'type': 'string'},
        {'key': 'admin_access_token', 'value': '', 'type': 'string'},
        {'key': 'main_mgr_access_token', 'value': '', 'type': 'string'},
        {'key': 'dept_mgr_access_token', 'value': '', 'type': 'string'},
        {'key': 'staff_access_token', 'value': '', 'type': 'string'},
        {'key': 'access_token', 'value': '', 'type': 'string'},
        {'key': 'token', 'value': '', 'type': 'string'},
        {'key': 'temp_token', 'value': '', 'type': 'string'},
        {'key': 'totp_secret', 'value': '', 'type': 'string'}
    ]

    for nv in needed_vars:
        if nv['key'] not in existing_vars:
            data.setdefault('variable', []).append(nv)
        else:
            if nv['key'] in ['base_url', 'baseUrl']:
                existing_vars[nv['key']]['value'] = 'http://127.0.0.1:8000'

    # 2. Update Admin Login Script
    auth_folder = next((i for i in data.get("item", []) if "Authentication" in i.get("name", "")), None)
    if auth_folder and "item" in auth_folder:
        admin_login = next((r for r in auth_folder["item"] if "Admin Login" in r.get("name", "")), None)
        if admin_login:
            admin_login["event"] = [
                {
                    "listen": "test",
                    "script": {
                        "type": "text/javascript",
                        "exec": [
                            "pm.test('Status code is 200 OK', function () { pm.response.to.have.status(200); });",
                            "if (pm.response.code === 200) {",
                            "    var data = pm.response.json();",
                            "    var token = data.access || data.token;",
                            "    if (token) {",
                            "        pm.collectionVariables.set('admin_token', token);",
                            "        pm.collectionVariables.set('admin_access_token', token);",
                            "        pm.collectionVariables.set('token', token);",
                            "        pm.collectionVariables.set('access_token', token);",
                            "        try { pm.environment.set('admin_token', token); } catch(e){}",
                            "        try { pm.environment.set('admin_access_token', token); } catch(e){}",
                            "        try { pm.environment.set('token', token); } catch(e){}",
                            "        try { pm.environment.set('access_token', token); } catch(e){}",
                            "        console.log('Admin token saved to collection variables and environment!');",
                            "    }",
                            "}"
                        ]
                    }
                }
            ]

    # Save to disk
    with open(target, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    with open("postman_collections/01_GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    print("Updated collection variables and scripts on disk.")

    # 3. Sync to Postman Cloud API
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
                print("Postman Cloud Sync: SUCCESS! Collection variables and URLs updated in Cloud.")
        except Exception as e:
            print(f"Cloud sync error: {e}")

if __name__ == "__main__":
    main()

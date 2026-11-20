import json

def patch_master_collection(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        col = json.load(f)

    admin_login_script = [
        "pm.test('Status code is 200 OK', function () {",
        "    pm.response.to.have.status(200);",
        "});",
        "",
        "if (pm.response.code === 200) {",
        "    var resData = pm.response.json();",
        "    var token = resData.access || resData.token;",
        "    if (token) {",
        "        pm.collectionVariables.set('admin_token', token);",
        "        pm.collectionVariables.set('adminToken', token);",
        "        try { pm.environment.set('admin_token', token); } catch(e){}",
        "        try { pm.environment.set('adminToken', token); } catch(e){}",
        "        console.log('Admin token saved successfully.');",
        "    }",
        "}"
    ]

    staff_change_pw_script = [
        "pm.test('Status code is 200 OK', function () {",
        "    pm.response.to.have.status(200);",
        "});",
        "",
        "if (pm.response.code === 200) {",
        "    var resData = pm.response.json();",
        "    var token = resData.access || resData.token;",
        "    if (token) {",
        "        pm.collectionVariables.set('staff_token', token);",
        "        pm.collectionVariables.set('staffToken', token);",
        "        try { pm.environment.set('staff_token', token); } catch(e){}",
        "        try { pm.environment.set('staffToken', token); } catch(e){}",
        "    }",
        "}"
    ]

    for item in col.get('item', []):
        if 'Staff Management' in item.get('name', ''):
            for sub in item.get('item', []):
                if 'Admin Staff Management' in sub.get('name', ''):
                    reqs = sub.get('item', [])
                    if not any('Admin Login' in r.get('name', '') for r in reqs):
                        admin_req = {
                            'name': '0. Admin Login (Populate {{admin_token}})',
                            'request': {
                                'method': 'POST',
                                'header': [{'key': 'Content-Type', 'value': 'application/json'}],
                                'body': {
                                    'mode': 'raw',
                                    'raw': '{\n  "email": "admin@bookmyroom.com",\n  "password": "AdminPassword123!"\n}'
                                },
                                'url': {
                                    'raw': '{{base_url}}/api/users/login/',
                                    'host': ['{{base_url}}'],
                                    'path': ['api', 'users', 'login', '']
                                },
                                'description': 'Authenticate as Admin to manage Staff.'
                            },
                            'event': [{
                                'listen': 'test',
                                'script': {
                                    'type': 'text/javascript',
                                    'exec': admin_login_script
                                }
                            }]
                        }
                        reqs.insert(0, admin_req)
                        print(f"Added Admin Login to {sub.get('name')}")
                elif 'Staff Authentication' in sub.get('name', ''):
                    for r in sub.get('item', []):
                        if 'Change Password' in r.get('name', ''):
                            r['event'] = [{
                                'listen': 'test',
                                'script': {
                                    'type': 'text/javascript',
                                    'exec': staff_change_pw_script
                                }
                            }]
                            print("Added test script to Staff Change Password")

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(col, f, indent=2)
    print('Updated', filepath)

patch_master_collection('GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json')
patch_master_collection('postman_collections/01_GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json')

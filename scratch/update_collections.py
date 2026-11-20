import json
import os

COLLECTION_PATH_ROOT = "GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json"
COLLECTION_PATH_SUB = os.path.join("postman_collections", "01_GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json")
STAFF_COLLECTION_PATH = os.path.join("postman_collections", "02_GOONSTAY_STAFF_MANAGEMENT_COLLECTION.json")
ENV_PATH = os.path.join("postman_collections", "04_GOONSTAY_POSTMAN_ENVIRONMENT.json")

def create_test_event(script_lines):
    return {
        "listen": "test",
        "script": {
            "type": "text/javascript",
            "exec": script_lines
        }
    }

def update_collection(filepath):
    if not os.path.exists(filepath):
        print(f"Skipping {filepath} (not found)")
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        col = json.load(f)

    # 1. Update Collection Variables
    vars_list = col.get("variable", [])
    var_dict = {v["key"]: v for v in vars_list}

    needed_vars = [
        {"key": "base_url", "value": "http://127.0.0.1:8000", "type": "string"},
        {"key": "baseUrl", "value": "http://127.0.0.1:8000", "type": "string"},
        {"key": "admin_token", "value": "", "type": "string"},
        {"key": "adminToken", "value": "", "type": "string"},
        {"key": "staff_token", "value": "", "type": "string"},
        {"key": "staffToken", "value": "", "type": "string"},
        {"key": "staff_refresh_token", "value": "", "type": "string"},
        {"key": "guest_token", "value": "", "type": "string"},
        {"key": "host_token", "value": "", "type": "string"},
        {"key": "token", "value": "", "type": "string"},
        {"key": "hotel_id", "value": "1", "type": "string"},
        {"key": "room_id", "value": "1", "type": "string"},
        {"key": "booking_id", "value": "1", "type": "string"},
        {"key": "review_id", "value": "1", "type": "string"},
        {"key": "coupon_code", "value": "WELCOME100", "type": "string"}
    ]

    for nv in needed_vars:
        if nv["key"] not in var_dict:
            vars_list.append(nv)
    col["variable"] = vars_list

    # 2. Scripts for different login types
    guest_login_script = [
        "pm.test('Status code is 200 OK', function () { pm.response.to.have.status(200); });",
        "",
        "if (pm.response.code === 200) {",
        "    var resData = pm.response.json();",
        "    var token = resData.access || resData.token;",
        "    if (token) {",
        "        pm.collectionVariables.set('guest_token', token);",
        "        pm.collectionVariables.set('token', token);",
        "        try { pm.environment.set('guest_token', token); } catch(e){}",
        "        try { pm.environment.set('token', token); } catch(e){}",
        "        console.log('Guest token updated successfully.');",
        "    }",
        "    if (resData.user && (resData.user.role === 'ADMIN' || resData.user.is_superuser || resData.user.is_staff)) {",
        "        pm.collectionVariables.set('admin_token', token);",
        "        pm.collectionVariables.set('adminToken', token);",
        "        try { pm.environment.set('admin_token', token); } catch(e){}",
        "        try { pm.environment.set('adminToken', token); } catch(e){}",
        "        console.log('Admin token updated successfully from login.');",
        "    }",
        "}"
    ]

    admin_login_script = [
        "pm.test('Status code is 200 OK', function () { pm.response.to.have.status(200); });",
        "",
        "if (pm.response.code === 200) {",
        "    var resData = pm.response.json();",
        "    var token = resData.access || resData.token;",
        "    if (token) {",
        "        pm.collectionVariables.set('admin_token', token);",
        "        pm.collectionVariables.set('adminToken', token);",
        "        pm.collectionVariables.set('token', token);",
        "        try { pm.environment.set('admin_token', token); } catch(e){}",
        "        try { pm.environment.set('adminToken', token); } catch(e){}",
        "        try { pm.environment.set('token', token); } catch(e){}",
        "        console.log('Admin tokens auto-saved successfully.');",
        "    }",
        "}"
    ]

    host_login_script = [
        "pm.test('Status code is 200 OK', function () { pm.response.to.have.status(200); });",
        "",
        "if (pm.response.code === 200) {",
        "    var resData = pm.response.json();",
        "    var token = resData.access || resData.token;",
        "    var refresh = resData.refresh;",
        "    if (token) {",
        "        pm.collectionVariables.set('host_token', token);",
        "        try { pm.environment.set('host_token', token); } catch(e){}",
        "    }",
        "    if (refresh) {",
        "        pm.collectionVariables.set('host_refresh', refresh);",
        "        try { pm.environment.set('host_refresh', refresh); } catch(e){}",
        "    }",
        "    console.log('Host token auto-saved successfully.');",
        "}"
    ]

    staff_login_script = [
        "pm.test('Status code is 200 OK', function () { pm.response.to.have.status(200); });",
        "",
        "if (pm.response.code === 200) {",
        "    var resData = pm.response.json();",
        "    var token = resData.access || resData.token || (resData.tokens && resData.tokens.access);",
        "    var refresh = resData.refresh || (resData.tokens && resData.tokens.refresh);",
        "    if (token) {",
        "        pm.collectionVariables.set('staff_token', token);",
        "        pm.collectionVariables.set('staffToken', token);",
        "        try { pm.environment.set('staff_token', token); } catch(e){}",
        "        try { pm.environment.set('staffToken', token); } catch(e){}",
        "        console.log('Staff token auto-saved successfully.');",
        "    }",
        "    if (refresh) {",
        "        pm.collectionVariables.set('staff_refresh_token', refresh);",
        "        try { pm.environment.set('staff_refresh_token', refresh); } catch(e){}",
        "    }",
        "}"
    ]

    def set_or_replace_test_event(item, script_lines):
        events = item.get("event", [])
        events = [ev for ev in events if ev.get("listen") != "test"]
        events.append(create_test_event(script_lines))
        item["event"] = events

    # Traverse items to attach scripts
    def walk_items(items):
        for item in items:
            name = item.get("name", "")
            if "item" in item:
                walk_items(item["item"])
            else:
                req = item.get("request", {})
                url_obj = req.get("url", {})
                raw_url = url_obj.get("raw", "") if isinstance(url_obj, dict) else str(url_obj)

                # Match Staff Login
                if "api/staff/login" in raw_url:
                    set_or_replace_test_event(item, staff_login_script)
                    print(f"Updated Staff Login script: {name}")

                # Match Host Login
                elif "api/users/host/login" in raw_url or "api/users/host-login" in raw_url:
                    set_or_replace_test_event(item, host_login_script)
                    print(f"Updated Host Login script: {name}")

                # Match User/Guest Login
                elif "api/users/login" in raw_url:
                    if "admin" in name.lower():
                        set_or_replace_test_event(item, admin_login_script)
                        print(f"Updated Admin Login script: {name}")
                    else:
                        set_or_replace_test_event(item, guest_login_script)
                        print(f"Updated Guest Login script: {name}")

    walk_items(col.get("item", []))

    # Check if a dedicated Admin Login exists in folder 01 and folder 14
    for folder in col.get("item", []):
        f_name = folder.get("name", "")
        # Folder 1: Authentication & Onboarding
        if "Authentication" in f_name and "item" in folder:
            has_admin_login = any("Admin Login" in x.get("name", "") for x in folder["item"])
            if not has_admin_login:
                admin_login_item = {
                    "name": "2b. Admin Login (Direct Admin Authentication)",
                    "request": {
                        "method": "POST",
                        "header": [
                            {"key": "Content-Type", "value": "application/json"}
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n  \"email\": \"admin@bookmyroom.com\",\n  \"password\": \"AdminPassword123!\"\n}"
                        },
                        "url": {
                            "raw": "{{base_url}}/api/users/login/",
                            "host": ["{{base_url}}"],
                            "path": ["api", "users", "login", ""]
                        },
                        "description": "Direct login for GoOnStay Administrator. Automatically populates {{admin_token}} and {{adminToken}}."
                    },
                    "event": [create_test_event(admin_login_script)]
                }
                # Insert right after User / Guest Login
                folder["item"].insert(2, admin_login_item)
                print(f"Added Admin Login item to {f_name}")

        # Folder 14: Super Admin Control Panel
        if "Super Admin Control Panel" in f_name and "item" in folder:
            has_admin_login = any("Admin Login" in x.get("name", "") for x in folder["item"])
            if not has_admin_login:
                admin_login_item = {
                    "name": "0. Admin Login (Populate {{admin_token}})",
                    "request": {
                        "method": "POST",
                        "header": [
                            {"key": "Content-Type", "value": "application/json"}
                        ],
                        "body": {
                            "mode": "raw",
                            "raw": "{\n  \"email\": \"admin@bookmyroom.com\",\n  \"password\": \"AdminPassword123!\"\n}"
                        },
                        "url": {
                            "raw": "{{base_url}}/api/users/login/",
                            "host": ["{{base_url}}"],
                            "path": ["api", "users", "login", ""]
                        },
                        "description": "Authenticate as Administrator to automatically set {{admin_token}} and {{adminToken}} for all Admin endpoints."
                    },
                    "event": [create_test_event(admin_login_script)]
                }
                folder["item"].insert(0, admin_login_item)
                print(f"Added Admin Login item to {f_name}")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(col, f, indent=2)
    print(f"Successfully updated and saved {filepath}")
    return col

# Execute update on both collection files
update_collection(COLLECTION_PATH_ROOT)
update_collection(COLLECTION_PATH_SUB)
update_collection(STAFF_COLLECTION_PATH)

# Update environment file
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        env_data = json.load(f)
    
    existing_keys = {v["key"]: v for v in env_data.get("values", [])}
    required_env_vars = [
        {"key": "base_url", "value": "http://127.0.0.1:8000", "type": "default", "enabled": True},
        {"key": "baseUrl", "value": "http://127.0.0.1:8000", "type": "default", "enabled": True},
        {"key": "admin_token", "value": "", "type": "default", "enabled": True},
        {"key": "adminToken", "value": "", "type": "default", "enabled": True},
        {"key": "staff_token", "value": "", "type": "default", "enabled": True},
        {"key": "staffToken", "value": "", "type": "default", "enabled": True},
        {"key": "staff_refresh_token", "value": "", "type": "default", "enabled": True},
        {"key": "guest_token", "value": "", "type": "default", "enabled": True},
        {"key": "host_token", "value": "", "type": "default", "enabled": True},
        {"key": "token", "value": "", "type": "default", "enabled": True},
    ]
    for r in required_env_vars:
        if r["key"] not in existing_keys:
            env_data.setdefault("values", []).append(r)
    
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        json.dump(env_data, f, indent=2)
    print(f"Successfully updated {ENV_PATH}")

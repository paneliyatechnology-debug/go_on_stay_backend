import json
import os

filepath = "GOONSTAY_STAFF_MANAGEMENT_POSTMAN.json"

with open(filepath, "r", encoding="utf-8") as f:
    col = json.load(f)

# Ensure collection variables have both camelCase and snake_case for maximum compatibility
vars_list = col.get("variable", [])
var_dict = {v["key"]: v for v in vars_list}

required_vars = [
    {"key": "baseUrl", "value": "http://127.0.0.1:8000", "type": "string"},
    {"key": "base_url", "value": "http://127.0.0.1:8000", "type": "string"},
    {"key": "staffToken", "value": "", "type": "string"},
    {"key": "staff_token", "value": "", "type": "string"},
    {"key": "staffRefreshToken", "value": "", "type": "string"},
    {"key": "staff_refresh_token", "value": "", "type": "string"},
    {"key": "adminToken", "value": "", "type": "string"},
    {"key": "admin_token", "value": "", "type": "string"},
]

for rv in required_vars:
    if rv["key"] not in var_dict:
        vars_list.append(rv)
col["variable"] = vars_list

def create_test_event(script_lines):
    return {
        "listen": "test",
        "script": {
            "type": "text/javascript",
            "exec": script_lines
        }
    }

staff_login_script = [
    "pm.test('Status code is 200 OK', function () {",
    "    pm.response.to.have.status(200);",
    "});",
    "",
    "if (pm.response.code === 200) {",
    "    var resData = pm.response.json();",
    "    var token = resData.access || resData.token || (resData.tokens && resData.tokens.access);",
    "    var refresh = resData.refresh || (resData.tokens && resData.tokens.refresh);",
    "",
    "    if (token) {",
    "        pm.collectionVariables.set('staffToken', token);",
    "        pm.collectionVariables.set('staff_token', token);",
    "        try { pm.environment.set('staffToken', token); } catch(e){}",
    "        try { pm.environment.set('staff_token', token); } catch(e){}",
    "        console.log('✅ Staff token extracted and saved to staffToken & staff_token.');",
    "    }",
    "    if (refresh) {",
    "        pm.collectionVariables.set('staffRefreshToken', refresh);",
    "        pm.collectionVariables.set('staff_refresh_token', refresh);",
    "        try { pm.environment.set('staffRefreshToken', refresh); } catch(e){}",
    "        try { pm.environment.set('staff_refresh_token', refresh); } catch(e){}",
    "    }",
    "}"
]

staff_change_password_script = [
    "pm.test('Status code is 200 OK', function () {",
    "    pm.response.to.have.status(200);",
    "});",
    "",
    "if (pm.response.code === 200) {",
    "    var resData = pm.response.json();",
    "    var token = resData.access || resData.token;",
    "    if (token) {",
    "        pm.collectionVariables.set('staffToken', token);",
    "        pm.collectionVariables.set('staff_token', token);",
    "        try { pm.environment.set('staffToken', token); } catch(e){}",
    "        try { pm.environment.set('staff_token', token); } catch(e){}",
    "        console.log('✅ Updated staff token after password change.');",
    "    }",
    "}"
]

admin_login_script = [
    "pm.test('Status code is 200 OK', function () {",
    "    pm.response.to.have.status(200);",
    "});",
    "",
    "if (pm.response.code === 200) {",
    "    var resData = pm.response.json();",
    "    var token = resData.access || resData.token;",
    "    if (token) {",
    "        pm.collectionVariables.set('adminToken', token);",
    "        pm.collectionVariables.set('admin_token', token);",
    "        try { pm.environment.set('adminToken', token); } catch(e){}",
    "        try { pm.environment.set('admin_token', token); } catch(e){}",
    "        console.log('✅ Admin token extracted and saved to adminToken & admin_token.');",
    "    }",
    "}"
]

# Update Staff Login & Change Password in Folder 1
for folder in col.get("item", []):
    f_name = folder.get("name", "")
    if "Staff Authentication" in f_name:
        for req in folder.get("item", []):
            if req.get("name") == "Staff Login":
                req["event"] = [create_test_event(staff_login_script)]
                print("Added test script to Staff Login")
            elif "Change Password" in req.get("name", ""):
                req["event"] = [create_test_event(staff_change_password_script)]
                print("Added test script to Staff Change Password")

    # Add Admin Login in Folder 2 (Admin Staff Management)
    if "Admin Staff Management" in f_name:
        items = folder.get("item", [])
        has_admin_login = any("Admin Login" in x.get("name", "") for x in items)
        if not has_admin_login:
            admin_login_item = {
                "name": "0. Admin Login (Populate {{adminToken}})",
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
                        "raw": "{{baseUrl}}/api/users/login/",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", "users", "login", ""]
                    },
                    "description": "Authenticate as Administrator to automatically set {{adminToken}} and {{admin_token}} for managing staff."
                },
                "event": [create_test_event(admin_login_script)]
            }
            items.insert(0, admin_login_item)
            print("Added 0. Admin Login to Admin Staff Management folder")

with open(filepath, "w", encoding="utf-8") as f:
    json.dump(col, f, indent=2)

print("Successfully updated", filepath)

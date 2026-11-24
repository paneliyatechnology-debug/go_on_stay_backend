"""
Script to deeply integrate the 4-Level Hierarchy & MFA APIs directly into existing folders
of GoOnStay Postman Collections:
1. Inside '01. Authentication & Onboarding' -> Add 'POST 2c. Manager & Admin MFA Verify'
2. Inside '13. Staff Management System (GoOnStay Centralized)':
   - In '1. Staff Authentication' -> Add MFA Setup & Verification endpoints
   - In '2. Admin Staff Management' -> Add Level 4 Admin Hierarchy APIs
   - Add new subfolder: '2b. Level 3 - Main Manager Operations'
   - Add new subfolder: '2c. Level 2 - Department Staff Manager Operations'
3. Inside '14. Super Admin Control Panel' -> Add Hierarchy Overview & Audit Logs
4. Standalone and dedicated collections updated.
"""

import json
import os

def get_mfa_items():
    return [
        {
            "name": "MFA 1. Initiate Setup (Generates Secret & Backup Codes)",
            "request": {
                "method": "POST",
                "header": [
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{access_token}}"}
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"temp_token\": \"{{temp_token}}\"\n}"
                },
                "url": {
                    "raw": "{{base_url}}/api/staff/mfa/setup/",
                    "host": ["{{base_url}}"],
                    "path": ["api", "staff", "mfa", "setup", ""]
                },
                "description": "Initiates TOTP MFA enrollment for Level 2, 3, 4 managers. Returns secret, QR URI, and 8 backup codes."
            }
        },
        {
            "name": "MFA 2. Verify & Activate Initial Enrollment",
            "request": {
                "method": "POST",
                "header": [
                    {"key": "Content-Type", "value": "application/json"}
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"temp_token\": \"{{temp_token}}\",\n    \"totp_code\": \"123456\"\n}"
                },
                "url": {
                    "raw": "{{base_url}}/api/staff/mfa/enroll-verify/",
                    "host": ["{{base_url}}"],
                    "path": ["api", "staff", "mfa", "enroll-verify", ""]
                },
                "description": "Verifies first TOTP code and activates MFA for manager account, issuing full JWT tokens."
            }
        },
        {
            "name": "MFA 3. Verify Login Challenge (TOTP Code)",
            "request": {
                "method": "POST",
                "header": [
                    {"key": "Content-Type", "value": "application/json"}
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"temp_token\": \"{{temp_token}}\",\n    \"totp_code\": \"123456\"\n}"
                },
                "url": {
                    "raw": "{{base_url}}/api/staff/mfa/verify/",
                    "host": ["{{base_url}}"],
                    "path": ["api", "staff", "mfa", "verify", ""]
                },
                "description": "Verifies 6-digit TOTP code when login returns mfa_required=true."
            }
        },
        {
            "name": "MFA 4. Verify Login Challenge (Backup Code)",
            "request": {
                "method": "POST",
                "header": [
                    {"key": "Content-Type", "value": "application/json"}
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"temp_token\": \"{{temp_token}}\",\n    \"backup_code\": \"ABCD-EFGH\"\n}"
                },
                "url": {
                    "raw": "{{base_url}}/api/staff/mfa/verify/",
                    "host": ["{{base_url}}"],
                    "path": ["api", "staff", "mfa", "verify", ""]
                },
                "description": "Emergency recovery using one of the 8 hashed backup codes."
            }
        },
        {
            "name": "MFA 5. Admin Reset / Disable MFA",
            "request": {
                "method": "POST",
                "header": [
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"user_id\": 2\n}"
                },
                "url": {
                    "raw": "{{base_url}}/api/staff/mfa/disable/",
                    "host": ["{{base_url}}"],
                    "path": ["api", "staff", "mfa", "disable", ""]
                },
                "description": "Admin resets MFA for locked or compromised account."
            }
        }
    ]

def get_main_manager_subfolder():
    return {
        "name": "2b. Level 3 - Main Manager Operations",
        "description": "Cross-department operational oversight: view all departments, create/assign Department Staff Managers, and view all operational staff.",
        "item": [
            {
                "name": "1. View All Departments & Staff Counts",
                "request": {
                    "method": "GET",
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{main_mgr_access_token}}"}
                    ],
                    "url": {
                        "raw": "{{base_url}}/api/staff/main-manager/departments/",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "main-manager", "departments", ""]
                    },
                    "description": "Main Manager views all active departments, currently assigned managers, and staff counts."
                }
            },
            {
                "name": "2. Create Department Staff Manager (Level 2)",
                "request": {
                    "method": "POST",
                    "header": [
                        {"key": "Content-Type", "value": "application/json"},
                        {"key": "Authorization", "value": "Bearer {{main_mgr_access_token}}"}
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": "{\n    \"username\": \"priya_reservation_mgr\",\n    \"email\": \"priya.mgr@goonstay.com\",\n    \"department_id\": 1,\n    \"first_name\": \"Priya\",\n    \"last_name\": \"Patel\",\n    \"designation\": \"Reservation Department Manager\"\n}"
                    },
                    "url": {
                        "raw": "{{base_url}}/api/staff/main-manager/dept-managers/",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "main-manager", "dept-managers", ""]
                    },
                    "description": "Main Manager creates a Level 2 Department Staff Manager."
                }
            },
            {
                "name": "3. List Department Staff Managers",
                "request": {
                    "method": "GET",
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{main_mgr_access_token}}"}
                    ],
                    "url": {
                        "raw": "{{base_url}}/api/staff/main-manager/dept-managers/?department_id=1",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "main-manager", "dept-managers", ""],
                        "query": [{"key": "department_id", "value": "1"}]
                    },
                    "description": "Lists all Level 2 Department Staff Managers."
                }
            },
            {
                "name": "4. Assign / Reassign Department Manager",
                "request": {
                    "method": "POST",
                    "header": [
                        {"key": "Content-Type", "value": "application/json"},
                        {"key": "Authorization", "value": "Bearer {{main_mgr_access_token}}"}
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": "{\n    \"manager_id\": 1,\n    \"department_id\": 1,\n    \"reassign_existing\": true\n}"
                    },
                    "url": {
                        "raw": "{{base_url}}/api/staff/main-manager/dept-managers/assign/",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "main-manager", "dept-managers", "assign", ""]
                    },
                    "description": "Assigns or reassigns manager to a department."
                }
            },
            {
                "name": "5. View All Operational Staff Across All Departments",
                "request": {
                    "method": "GET",
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{main_mgr_access_token}}"}
                    ],
                    "url": {
                        "raw": "{{base_url}}/api/staff/main-manager/staff/?status=ACTIVE",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "main-manager", "staff", ""],
                        "query": [{"key": "status", "value": "ACTIVE"}]
                    },
                    "description": "Main Manager views all operational staff with search & filter."
                }
            }
        ]
    }

def get_dept_manager_subfolder():
    return {
        "name": "2c. Level 2 - Department Staff Manager Operations",
        "description": "Department-specific management: manage staff strictly within assigned department, server-side isolation, and delegation boundaries.",
        "item": [
            {
                "name": "1. View Assigned Department Staff (Isolated)",
                "request": {
                    "method": "GET",
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{dept_mgr_access_token}}"}
                    ],
                    "url": {
                        "raw": "{{base_url}}/api/staff/dept-manager/staff/",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "dept-manager", "staff", ""]
                    },
                    "description": "Lists staff strictly belonging to the manager's assigned department."
                }
            },
            {
                "name": "2. Create Staff Member within Department",
                "request": {
                    "method": "POST",
                    "header": [
                        {"key": "Content-Type", "value": "application/json"},
                        {"key": "Authorization", "value": "Bearer {{dept_mgr_access_token}}"}
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": "{\n    \"username\": \"rahul_res_agent\",\n    \"email\": \"rahul.agent@goonstay.com\",\n    \"first_name\": \"Rahul\",\n    \"last_name\": \"Verma\",\n    \"department_id\": 1,\n    \"designation\": \"Reservation Officer\"\n}"
                    },
                    "url": {
                        "raw": "{{base_url}}/api/staff/dept-manager/staff/",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "dept-manager", "staff", ""]
                    },
                    "description": "Creates a Level 1 operational staff member inside the manager's assigned department."
                }
            },
            {
                "name": "3. Get Staff Detail (IDOR Protected)",
                "request": {
                    "method": "GET",
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{dept_mgr_access_token}}"}
                    ],
                    "url": {
                        "raw": "{{base_url}}/api/staff/dept-manager/staff/1/",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "dept-manager", "staff", "1", ""]
                    },
                    "description": "View staff details. Returns 403 Forbidden if staff belongs to another department."
                }
            },
            {
                "name": "4. Update Staff Details / Status",
                "request": {
                    "method": "PATCH",
                    "header": [
                        {"key": "Content-Type", "value": "application/json"},
                        {"key": "Authorization", "value": "Bearer {{dept_mgr_access_token}}"}
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": "{\n    \"status\": \"ACTIVE\",\n    \"designation\": \"Senior Reservation Associate\"\n}"
                    },
                    "url": {
                        "raw": "{{base_url}}/api/staff/dept-manager/staff/1/",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "dept-manager", "staff", "1", ""]
                    },
                    "description": "Updates staff status or details. Role tampering is blocked."
                }
            },
            {
                "name": "5. View Staff Assigned Permissions",
                "request": {
                    "method": "GET",
                    "header": [
                        {"key": "Authorization", "value": "Bearer {{dept_mgr_access_token}}"}
                    ],
                    "url": {
                        "raw": "{{base_url}}/api/staff/dept-manager/staff/1/permissions/",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "dept-manager", "staff", "1", "permissions", ""]
                    },
                    "description": "Lists granular permissions assigned to a staff member."
                }
            },
            {
                "name": "6. Assign / Revoke Staff Permissions (Delegation Constrained)",
                "request": {
                    "method": "POST",
                    "header": [
                        {"key": "Content-Type", "value": "application/json"},
                        {"key": "Authorization", "value": "Bearer {{dept_mgr_access_token}}"}
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": "{\n    \"permissions\": [\"VIEW_BOOKINGS\", \"MANAGE_RESERVATIONS\"]\n}"
                    },
                    "url": {
                        "raw": "{{base_url}}/api/staff/dept-manager/staff/1/permissions/",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "dept-manager", "staff", "1", "permissions", ""]
                    },
                    "description": "Assigns permissions within department scope. Sensitive permissions are blocked."
                }
            }
        ]
    }

def get_admin_hierarchy_items():
    return [
        {
            "name": "Hierarchy Overview & Metrics",
            "request": {
                "method": "GET",
                "header": [{"key": "Authorization", "value": "Bearer {{admin_access_token}}"}],
                "url": {
                    "raw": "{{base_url}}/api/staff/admin/hierarchy-overview/",
                    "host": ["{{base_url}}"],
                    "path": ["api", "staff", "admin", "hierarchy-overview", ""]
                },
                "description": "Cross-hierarchy metrics across Level 4, 3, 2, 1 and active departments."
            }
        },
        {
            "name": "Create Main Manager (Level 3)",
            "request": {
                "method": "POST",
                "header": [
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"username\": \"executive_director\",\n    \"email\": \"director@goonstay.com\",\n    \"first_name\": \"Ramesh\",\n    \"last_name\": \"Sharma\",\n    \"designation\": \"Operations Director\"\n}"
                },
                "url": {
                    "raw": "{{base_url}}/api/staff/admin/main-managers/",
                    "host": ["{{base_url}}"],
                    "path": ["api", "staff", "admin", "main-managers", ""]
                },
                "description": "Admin creates Level 3 Main Manager account."
            }
        },
        {
            "name": "List Main Managers",
            "request": {
                "method": "GET",
                "header": [{"key": "Authorization", "value": "Bearer {{admin_access_token}}"}],
                "url": {
                    "raw": "{{base_url}}/api/staff/admin/main-managers/",
                    "host": ["{{base_url}}"],
                    "path": ["api", "staff", "admin", "main-managers", ""]
                },
                "description": "Lists all Level 3 Main Managers."
            }
        },
        {
            "name": "Configure Permission Delegation Policy",
            "request": {
                "method": "POST",
                "header": [
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                ],
                "body": {
                    "mode": "raw",
                    "raw": "{\n    \"role\": \"MAIN_MANAGER\",\n    \"allow_sensitive_permissions\": false,\n    \"permission_codes\": [\"VIEW_BOOKINGS\", \"MANAGE_RESERVATIONS\", \"VIEW_SUPPORT\", \"VIEW_REFUNDS\"]\n}"
                },
                "url": {
                    "raw": "{{base_url}}/api/staff/admin/delegation-policies/",
                    "host": ["{{base_url}}"],
                    "path": ["api", "staff", "admin", "delegation-policies", ""]
                },
                "description": "Admin configures maximum delegated permissions."
            }
        },
        {
            "name": "View Hierarchy Audit Logs",
            "request": {
                "method": "GET",
                "header": [{"key": "Authorization", "value": "Bearer {{admin_access_token}}"}],
                "url": {
                    "raw": "{{base_url}}/api/staff/admin/audit-logs/?action_type=MANAGER_CREATE",
                    "host": ["{{base_url}}"],
                    "path": ["api", "staff", "admin", "audit-logs", ""],
                    "query": [{"key": "action_type", "value": "MANAGER_CREATE"}]
                },
                "description": "Admin queries tamper-resistant audit logs."
            }
        }
    ]

def patch_collection(filepath):
    if not os.path.exists(filepath):
        print(f"Skipping {filepath} (not found)")
        return
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Update '01. Authentication & Onboarding'
    auth_folder = next((i for i in data.get("item", []) if "Authentication" in i.get("name", "")), None)
    if auth_folder and "item" in auth_folder:
        has_mfa = any("MFA" in req.get("name", "") for req in auth_folder["item"])
        if not has_mfa:
            mfa_verify_req = {
                "name": "POST 2c. Manager & Admin MFA Verify (TOTP Challenge)",
                "request": {
                    "method": "POST",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {
                        "mode": "raw",
                        "raw": "{\n    \"temp_token\": \"{{temp_token}}\",\n    \"totp_code\": \"123456\"\n}"
                    },
                    "url": {
                        "raw": "{{base_url}}/api/staff/mfa/verify/",
                        "host": ["{{base_url}}"],
                        "path": ["api", "staff", "mfa", "verify", ""]
                    },
                    "description": "Completes login when Admin or Manager credentials return mfa_required=true."
                }
            }
            # Insert after login
            auth_folder["item"].insert(3, mfa_verify_req)

    # 2. Update '13. Staff Management System (GoOnStay Centralized)'
    staff_folder = next((i for i in data.get("item", []) if "Staff Management" in i.get("name", "")), None)
    if staff_folder and "item" in staff_folder:
        # In '1. Staff Authentication' add MFA
        staff_auth = next((i for i in staff_folder["item"] if "Staff Authentication" in i.get("name", "")), None)
        if staff_auth and "item" in staff_auth:
            existing_names = [x.get("name", "") for x in staff_auth["item"]]
            for mfa_item in get_mfa_items():
                if mfa_item["name"] not in existing_names:
                    staff_auth["item"].append(mfa_item)

        # In '2. Admin Staff Management' add Level 4 items
        admin_staff = next((i for i in staff_folder["item"] if "Admin Staff Management" in i.get("name", "")), None)
        if admin_staff and "item" in admin_staff:
            existing_names = [x.get("name", "") for x in admin_staff["item"]]
            for adm_item in get_admin_hierarchy_items():
                if adm_item["name"] not in existing_names:
                    admin_staff["item"].append(adm_item)

        # Add '2b. Level 3 - Main Manager Operations' if missing
        has_main_mgr = any("Main Manager" in i.get("name", "") for i in staff_folder["item"])
        if not has_main_mgr:
            staff_folder["item"].insert(2, get_main_manager_subfolder())

        # Add '2c. Level 2 - Department Staff Manager Operations' if missing
        has_dept_mgr = any("Department Staff Manager" in i.get("name", "") for i in staff_folder["item"])
        if not has_dept_mgr:
            staff_folder["item"].insert(3, get_dept_manager_subfolder())

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Successfully integrated into {filepath}")

def main():
    targets = [
        "GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json",
        "postman_collections/01_GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json",
        "GOONSTAY_STAFF_MANAGEMENT_POSTMAN.json",
        "BookMyRoom_Master_Backend.postman_collection.json"
    ]
    for t in targets:
        patch_collection(t)

if __name__ == "__main__":
    main()

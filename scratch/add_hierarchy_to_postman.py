"""
Script to generate standalone 4-Level Admin & Staff Hierarchy Postman Collection
and inject it into the Master GoOnStay Postman Collection.
"""

import json
import os

def create_hierarchy_folder():
    return {
        "name": "16. 4-Level Admin & Staff Hierarchy + Manager MFA",
        "description": "Complete production-grade Four-Level Hierarchy (Admin > Main Manager > Dept Manager > Staff) and Mandatory TOTP Multi-Factor Authentication.",
        "item": [
            # 1. MFA
            {
                "name": "01. Multi-Factor Authentication (MFA)",
                "description": "Mandatory TOTP Multi-Factor Authentication for Level 2 (Dept Manager), Level 3 (Main Manager), and Level 4 (Admin).",
                "item": [
                    {
                        "name": "1. Initiate MFA Setup (Generates Secret & Backup Codes)",
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
                            "description": "Initiates TOTP MFA enrollment. Generates Base32 secret, otpauth:// provisioning URI, 8 hashed backup codes, and a confirmation temp_token."
                        }
                    },
                    {
                        "name": "2. Verify & Activate Initial MFA Enrollment",
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
                            "description": "Verifies first 6-digit TOTP code from Google/Microsoft Authenticator, activates MFA, and issues JWT access tokens."
                        }
                    },
                    {
                        "name": "3. Verify Login Challenge with TOTP Code",
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
                            "description": "Completes 2-step login for managers and admins when login returns mfa_required=true."
                        }
                    },
                    {
                        "name": "4. Verify Login Challenge with Backup Recovery Code",
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
                            "description": "Emergency recovery using one of the 8 one-time backup codes. The code is consumed and cannot be reused."
                        }
                    },
                    {
                        "name": "5. Admin Reset / Disable Account MFA",
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
                            "description": "Admin-only reset of MFA secret and lockout for a locked or lost authenticator device."
                        }
                    }
                ]
            },

            # 2. Level 4: Administrator
            {
                "name": "02. Level 4 - Administrator Hierarchy Control",
                "description": "System-wide authority: Main Manager creation, department management, delegation policies, and complete audit logging.",
                "item": [
                    {
                        "name": "1. Hierarchy System Overview & Metrics",
                        "request": {
                            "method": "GET",
                            "header": [
                                {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                            ],
                            "url": {
                                "raw": "{{base_url}}/api/staff/admin/hierarchy-overview/",
                                "host": ["{{base_url}}"],
                                "path": ["api", "staff", "admin", "hierarchy-overview", ""]
                            },
                            "description": "Returns counts for Level 4 Admins, Level 3 Main Managers, Level 2 Dept Managers, Level 1 Staff, and department breakdown."
                        }
                    },
                    {
                        "name": "2. Create Main Manager (Level 3)",
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
                            "description": "Admin creates a Level 3 Main Manager account. Automatically creates staff profile with all-department oversight and initial MFA profile."
                        }
                    },
                    {
                        "name": "3. List All Main Managers",
                        "request": {
                            "method": "GET",
                            "header": [
                                {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                            ],
                            "url": {
                                "raw": "{{base_url}}/api/staff/admin/main-managers/",
                                "host": ["{{base_url}}"],
                                "path": ["api", "staff", "admin", "main-managers", ""]
                            },
                            "description": "Lists all active and registered Level 3 Main Managers."
                        }
                    },
                    {
                        "name": "4. Create New Department",
                        "request": {
                            "method": "POST",
                            "header": [
                                {"key": "Content-Type", "value": "application/json"},
                                {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                            ],
                            "body": {
                                "mode": "raw",
                                "raw": "{\n    \"code\": \"MARKETING\",\n    \"name\": \"Marketing & Growth\",\n    \"description\": \"Campaigns, promotions, and brand growth\"\n}"
                            },
                            "url": {
                                "raw": "{{base_url}}/api/staff/admin/departments/",
                                "host": ["{{base_url}}"],
                                "path": ["api", "staff", "admin", "departments", ""]
                            },
                            "description": "Admin creates a new system department."
                        }
                    },
                    {
                        "name": "5. List All Departments (Admin View)",
                        "request": {
                            "method": "GET",
                            "header": [
                                {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                            ],
                            "url": {
                                "raw": "{{base_url}}/api/staff/admin/departments/",
                                "host": ["{{base_url}}"],
                                "path": ["api", "staff", "admin", "departments", ""]
                            },
                            "description": "Lists all departments with active status and timestamps."
                        }
                    },
                    {
                        "name": "6. Update Department Status / Details",
                        "request": {
                            "method": "PATCH",
                            "header": [
                                {"key": "Content-Type", "value": "application/json"},
                                {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                            ],
                            "body": {
                                "mode": "raw",
                                "raw": "{\n    \"is_active\": true,\n    \"name\": \"Reservation & Guest Booking\"\n}"
                            },
                            "url": {
                                "raw": "{{base_url}}/api/staff/admin/departments/1/",
                                "host": ["{{base_url}}"],
                                "path": ["api", "staff", "admin", "departments", "1", ""]
                            },
                            "description": "Admin updates or activates/deactivates a department."
                        }
                    },
                    {
                        "name": "7. Configure Permission Delegation Policy",
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
                            "description": "Admin defines maximum delegation limits and whether sensitive permissions may be granted."
                        }
                    },
                    {
                        "name": "8. View Delegation Policies",
                        "request": {
                            "method": "GET",
                            "header": [
                                {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                            ],
                            "url": {
                                "raw": "{{base_url}}/api/staff/admin/delegation-policies/",
                                "host": ["{{base_url}}"],
                                "path": ["api", "staff", "admin", "delegation-policies", ""]
                            },
                            "description": "View configured delegation policies for Main Manager and Department Staff Manager."
                        }
                    },
                    {
                        "name": "9. View Permission Catalogue (Sensitive Flags)",
                        "request": {
                            "method": "GET",
                            "header": [
                                {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                            ],
                            "url": {
                                "raw": "{{base_url}}/api/staff/admin/permissions/",
                                "host": ["{{base_url}}"],
                                "path": ["api", "staff", "admin", "permissions", ""]
                            },
                            "description": "Lists granular permissions with category, department, and sensitive flag."
                        }
                    },
                    {
                        "name": "10. View Tamper-Resistant Hierarchy Audit Logs",
                        "request": {
                            "method": "GET",
                            "header": [
                                {"key": "Authorization", "value": "Bearer {{admin_access_token}}"}
                            ],
                            "url": {
                                "raw": "{{base_url}}/api/staff/admin/audit-logs/?action_type=MANAGER_CREATE",
                                "host": ["{{base_url}}"],
                                "path": ["api", "staff", "admin", "audit-logs", ""],
                                "query": [
                                    {"key": "action_type", "value": "MANAGER_CREATE"}
                                ]
                            },
                            "description": "Admin queries audit logs for sensitive operations with filters for actor, role, department, and action."
                        }
                    }
                ]
            },

            # 3. Level 3: Main Manager
            {
                "name": "03. Level 3 - Main Manager Operations",
                "description": "Cross-department operational oversight: view departments, create/assign Department Staff Managers, and view all operational staff.",
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
                            "description": "Main Manager creates a Level 2 Department Staff Manager and assigns them to an active department."
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
                                "query": [
                                    {"key": "department_id", "value": "1"}
                                ]
                            },
                            "description": "Lists all Level 2 Department Staff Managers, optionally filtered by department ID."
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
                            "description": "Assigns or reassigns an existing Department Staff Manager to a department, revoking previous active assignments if requested."
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
                                "raw": "{{base_url}}/api/staff/main-manager/staff/?department_id=1&status=ACTIVE",
                                "host": ["{{base_url}}"],
                                "path": ["api", "staff", "main-manager", "staff", ""],
                                "query": [
                                    {"key": "department_id", "value": "1"},
                                    {"key": "status", "value": "ACTIVE"}
                                ]
                            },
                            "description": "Main Manager views staff across all departments with search and filtering."
                        }
                    }
                ]
            },

            # 4. Level 2: Department-wise Staff Manager
            {
                "name": "04. Level 2 - Department Staff Manager Operations",
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
                            "description": "Lists staff strictly belonging to the manager's assigned department. Staff from other departments are hidden."
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
                            "description": "Creates a Level 1 operational staff member inside the manager's assigned department. Cannot create staff for other departments."
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
                            "description": "View staff details. Returns 403 Forbidden if the staff member belongs to another department or is higher authority."
                        }
                    },
                    {
                        "name": "4. Update Staff Details / Status (Activate / Suspend)",
                        "request": {
                            "method": "PATCH",
                            "header": [
                                {"key": "Content-Type", "value": "application/json"},
                                {"key": "Authorization", "value": "Bearer {{dept_mgr_access_token}}"}
                            ],
                            "body": {
                                "mode": "raw",
                                "raw": "{\n    \"status\": \"ACTIVE\",\n    \"designation\": \"Senior Reservation Associate\",\n    \"phone_number\": \"+919876543210\"\n}"
                            },
                            "url": {
                                "raw": "{{base_url}}/api/staff/dept-manager/staff/1/",
                                "host": ["{{base_url}}"],
                                "path": ["api", "staff", "dept-manager", "staff", "1", ""]
                            },
                            "description": "Updates staff status or personal info. Role tampering is strictly blocked."
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
                            "description": "Lists granular permissions assigned to a department staff member."
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
                            "description": "Assigns permissions within manager's department scope. Sensitive permissions or permissions from other departments are rejected with 403 Forbidden."
                        }
                    }
                ]
            }
        ]
    }

def main():
    folder = create_hierarchy_folder()
    
    # 1. Create Standalone Postman Collection
    standalone = {
        "info": {
            "_postman_id": "goonstay-4-level-hierarchy-and-mfa-v1",
            "name": "GoOnStay - 4-Level Admin & Staff Hierarchy + Manager MFA",
            "description": "Dedicated Postman collection for GoOnStay 4-Level Admin & Staff Hierarchy (Admin, Main Manager, Department Staff Manager, Staff) and Mandatory TOTP MFA.",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "item": folder["item"]
    }
    
    with open("GOONSTAY_4_LEVEL_ADMIN_STAFF_HIERARCHY_POSTMAN.json", "w", encoding="utf-8") as f:
        json.dump(standalone, f, indent=2)
    print("Created GOONSTAY_4_LEVEL_ADMIN_STAFF_HIERARCHY_POSTMAN.json")

    # 2. Update Master Collections
    targets = [
        "GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json",
        "postman_collections/01_GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json"
    ]
    for target in targets:
        if os.path.exists(target):
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Remove any existing folder with same name
            data["item"] = [i for i in data.get("item", []) if not i["name"].startswith("16. 4-Level")]
            data["item"].append(folder)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"Updated {target}")

if __name__ == "__main__":
    main()

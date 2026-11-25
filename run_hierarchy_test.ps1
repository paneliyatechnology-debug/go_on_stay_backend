# GoOnStay 4-Level Admin & Staff Hierarchy Automation Test Script
# Usage: powershell -ExecutionPolicy Bypass -File run_hierarchy_test.ps1

$BaseUrl = "http://127.0.0.1:8000"
$Timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   GoOnStay 4-Level Admin & Staff Hierarchy Test Flow     " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# -----------------------------------------------------------------------------
# STEP 1: Admin Login (Level 4)
# -----------------------------------------------------------------------------
Write-Host "`n[Step 1] Logging in as Platform Admin (admin@bookmyroom.com)..." -ForegroundColor Yellow
try {
    $adminLogin = Invoke-RestMethod -Uri "$BaseUrl/api/users/login/" -Method Post -ContentType "application/json" -Body '{"email":"admin@bookmyroom.com","password":"admin123"}'
    $adminToken = $adminLogin.access
    Write-Host "  ✔ Admin Login Successful! Token received." -ForegroundColor Green
} catch {
    Write-Host "  ✖ Admin Login Failed!" -ForegroundColor Red
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "  Response: " $reader.ReadToEnd() -ForegroundColor Red
    } else {
        Write-Host "  Error: Server not reachable at $BaseUrl. Please make sure Django server is running." -ForegroundColor Red
    }
    exit 1
}

# -----------------------------------------------------------------------------
# STEP 2: Create Main Manager (Level 3)
# -----------------------------------------------------------------------------
$mgrUsername = "mgr_$Timestamp"
$mgrEmail = "mgr_$Timestamp@goonstay.com"
$mgrPhone = "+9198" + (Get-Random -Minimum 10000000 -Maximum 99999999)
$mgrPassword = "ManagerPassword123!"

Write-Host "`n[Step 2] Admin creating Main Manager ($mgrUsername)..." -ForegroundColor Yellow
try {
    $headers = @{ Authorization = "Bearer $adminToken" }
    $mgrBody = @{
        username = $mgrUsername
        email = $mgrEmail
        first_name = "Vikram"
        last_name = "Sharma"
        phone_number = $mgrPhone
        designation = "Operations Director"
        password = $mgrPassword
    } | ConvertTo-Json

    $mgrRes = Invoke-RestMethod -Uri "$BaseUrl/api/staff/admin/main-managers/" -Method Post -ContentType "application/json" -Headers $headers -Body $mgrBody
    Write-Host "  ✔ Main Manager Created: $($mgrRes.data.username) (ID: $($mgrRes.data.id))" -ForegroundColor Green
} catch {
    Write-Host "  ✖ Manager Creation Failed!" -ForegroundColor Red
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "  Response: " $reader.ReadToEnd() -ForegroundColor Red
    }
    exit 1
}

# -----------------------------------------------------------------------------
# STEP 3: Main Manager Login & TOTP MFA Enrollment
# -----------------------------------------------------------------------------
Write-Host "`n[Step 3a] Initiating Manager Login (MFA Challenge)..." -ForegroundColor Yellow
try {
    $mgrLoginBody = @{
        identifier = $mgrUsername
        password = $mgrPassword
    } | ConvertTo-Json

    $mgrLoginRes = Invoke-RestMethod -Uri "$BaseUrl/api/staff/login/" -Method Post -ContentType "application/json" -Body $mgrLoginBody
    $tempToken = $mgrLoginRes.temp_token
    $mfaSecret = $mgrLoginRes.secret
    Write-Host "  ✔ MFA Required! Received Temp Token & Secret ($mfaSecret)" -ForegroundColor Green

    Write-Host "`n[Step 3b] Generating RFC 6238 6-Digit TOTP Code..." -ForegroundColor Yellow
    $totpCode = (.\venv\Scripts\python.exe -c "from util.totp import generate_totp_code; print(generate_totp_code('$mfaSecret'))").Trim()
    Write-Host "  ✔ Generated Live OTP: $totpCode" -ForegroundColor Cyan

    $verifyBody = @{
        temp_token = $tempToken
        totp_code = $totpCode
    } | ConvertTo-Json

    $mfaVerifyRes = Invoke-RestMethod -Uri "$BaseUrl/api/staff/mfa/enroll-verify/" -Method Post -ContentType "application/json" -Body $verifyBody
    $mgrToken = $mfaVerifyRes.access
    Write-Host "  ✔ MFA Verified & Activated! Manager Token received." -ForegroundColor Green
} catch {
    Write-Host "  ✖ Manager MFA Flow Failed!" -ForegroundColor Red
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "  Response: " $reader.ReadToEnd() -ForegroundColor Red
    }
    exit 1
}

# -----------------------------------------------------------------------------
# STEP 4: Create Department Staff (Level 1)
# -----------------------------------------------------------------------------
$staffEmail = "staff_$Timestamp@goonstay.com"
$staffPhone = "+9197" + (Get-Random -Minimum 10000000 -Maximum 99999999)
$staffPassword = "StaffPassword123!"

Write-Host "`n[Step 4] Creating Department Staff ($staffEmail)..." -ForegroundColor Yellow
try {
    $staffBody = @{
        first_name = "Karan"
        last_name = "Verma"
        email = $staffEmail
        phone_number = $staffPhone
        department_id = 1
        designation = "Booking Operator"
        password = $staffPassword
    } | ConvertTo-Json

    $staffRes = Invoke-RestMethod -Uri "$BaseUrl/api/staff/create/" -Method Post -ContentType "application/json" -Headers $headers -Body $staffBody
    $staffId = $staffRes.data.id
    $staffLoginId = $staffRes.login_id
    $staffGeneratedPassword = $staffRes.temporary_password
    Write-Host "  ✔ Staff Created: $staffLoginId (Email: $staffEmail)" -ForegroundColor Green
    Write-Host "  ✔ Temporary Password: $staffGeneratedPassword" -ForegroundColor Cyan
} catch {
    Write-Host "  ✖ Staff Creation Failed!" -ForegroundColor Red
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "  Response: " $reader.ReadToEnd() -ForegroundColor Red
    }
    exit 1
}

# -----------------------------------------------------------------------------
# STEP 5: Staff Direct Login (No OTP / No MFA Required)
# -----------------------------------------------------------------------------
Write-Host "`n[Step 5] Staff Direct Login (No MFA Required)..." -ForegroundColor Yellow
try {
    $staffLoginBody = @{
        identifier = $staffLoginId
        password = $staffGeneratedPassword
    } | ConvertTo-Json

    $staffLoginRes = Invoke-RestMethod -Uri "$BaseUrl/api/staff/login/" -Method Post -ContentType "application/json" -Body $staffLoginBody
    Write-Host "  ✔ Staff Logged In Directly! Level 1 JWT Access Token:" -ForegroundColor Green
    Write-Host "    $($staffLoginRes.tokens.access.Substring(0, 45))..." -ForegroundColor DarkCyan
} catch {
    Write-Host "  ✖ Staff Login Failed!" -ForegroundColor Red
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        Write-Host "  Response: " $reader.ReadToEnd() -ForegroundColor Red
    }
    exit 1
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host "  ALL 5 STEPS PASSED SUCCESSFULLY! HIERARCHY IS WORKING!  " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green

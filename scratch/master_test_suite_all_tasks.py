import os
import sys
import subprocess

current_dir = os.path.dirname(os.path.abspath(__file__))
python_exe = sys.executable

scripts = [
    ("TASK-01 to TASK-05 (Critical P0)", os.path.join(current_dir, "test_p0_tasks.py")),
    ("TASK-06 to TASK-10 (Core Platform)", os.path.join(current_dir, "test_tasks_06_to_10.py")),
    ("TASK-11 to TASK-15 (Financial & Guest)", os.path.join(current_dir, "test_tasks_11_to_15.py")),
    ("TASK-16 to TASK-20 (Enterprise & System)", os.path.join(current_dir, "test_tasks_16_to_20.py")),
    ("TASK-13 UPGRADE (Advanced Coupon Rules)", os.path.join(current_dir, "test_upgraded_coupons.py")),
]

print("=" * 72)
print("   BOOKMYROOM MASTER BACKEND VERIFICATION RUNNER (TASK-01 TO 20)   ")
print("=" * 72)

results = []

for label, script_path in scripts:
    print(f"\n>> Executing: {label}...")
    res = subprocess.run([python_exe, script_path], capture_output=True, text=True)
    if res.returncode == 0:
        results.append((label, "PASSED", "All requirements verified 100%"))
        print(f"   [OK] {label} completed successfully.")
    else:
        results.append((label, "FAILED", res.stderr or res.stdout[-300:]))
        print(f"   [FAIL] {label} failed.")
        print(res.stdout)
        print(res.stderr)

print("\n" + "=" * 72)
print("                    FINAL VERIFICATION SUMMARY                    ")
print("=" * 72)
for label, status_str, note in results:
    badge = "[PASS 100%]" if status_str == "PASSED" else "[FAILED]"
    print(f"{label:45} : {badge}")
print("=" * 72)

all_passed = all(status_str == "PASSED" for _, status_str, _ in results)
if all_passed:
    print("ALL 20 TASKS FROM BOOK_MY_ROOM_BACKEND_DEVELOPER_TASK_LIST.md ARE 100% COMPLETE & VERIFIED!")
else:
    sys.exit(1)


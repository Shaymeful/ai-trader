# Windows Python Re-Exec Fix

## Problem

Windows exhibits a python->python double-launch/re-exec issue where running a loop produces TWO processes with identical command lines and start times:

- Parent PID 30604 (ParentProcessId 38420)
- Child  PID 50044 (ParentProcessId 30604)

Both running:
```
"C:\dev\ai-trader\.venv\Scripts\python.exe" -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run
```

**Impact**: Despite the existing mutex/file lock guard, both processes were running concurrently, potentially causing duplicate trades or state corruption.

---

## Root Cause

When using `python -m module.name`, Windows can spawn a child python.exe process that re-executes the same command. This is a known Windows + Python behavior related to how the `-m` flag resolves modules.

The existing single-instance guard ran AFTER argument parsing and module initialization, which was too late to catch the child process before it acquired resources.

---

## Solution

### 1. Early Parent Process Detection

Added `_check_parent_is_runner()` function that detects if the parent process is another python.exe running the runner. This runs **before** the mutex/file lock guard, providing an immediate exit path for re-exec children.

**Location**: `src/app/runner.py:729-792`

**Detection logic**:
- Query parent process using pywin32 (`win32api.OpenProcess`)
- Check if parent is `python.exe`
- Query command line via WMI to confirm it's running runner
- Exit immediately with code 99 if detected

**Benefits**:
- Catches re-exec children before they can interfere
- Provides clear diagnostics showing both parent and child PIDs
- Exit code 99 distinguishes re-exec children from other failures

### 2. Scheduler Wrapper Update

Updated Task Scheduler wrapper but **continues to use `-m`** for proper module imports:

**Command** (unchanged):
```powershell
python.exe -m src.app.runner --mode paper --loop ...
```

**Location**: `tools/run_paper_dryrun.ps1`

**What changed**:
- Removed PowerShell file lock (Python guard is authoritative)
- Improved logging (shows python path, module, working directory)
- Simplified logic (wrapper just launches and waits)

**Why keep `-m`**:
- Required for proper Python module imports (direct runner.py breaks imports)
- Early parent detection handles re-exec children immediately (exit code 99)
- The `-m` flag may trigger re-exec, but the child is caught and exits instantly

**Benefits**:
- Python single-instance guard is the authoritative source of truth
- Re-exec children are detected and terminated immediately
- Cleaner wrapper code with better diagnostics

### 3. Enhanced Guard Diagnostics

When a child process is detected, clear output shows:

```
================================================================================
DETECTED RUNNER CHILD PROCESS - EXITING IMMEDIATELY
================================================================================
This process (child):
  PID:         50044
  Interpreter: C:\dev\ai-trader\.venv\Scripts\python.exe
  Arguments:   -m src.app.runner --mode paper --loop ...

Parent process (runner):
  PID:         30604
  Name:        python.exe
  CommandLine: python.exe -m src.app.runner --mode paper --loop ...

Windows python->python re-exec detected. Child process exiting.
Only the parent runner process should continue running.
================================================================================
```

Exit codes:
- **99**: Re-exec child detected (early exit)
- **1**: Guard blocked (mutex/file lock already held)
- **0**: Normal exit

### 4. Verification Script

Created `tools/verify_single_instance_loop.ps1` to properly test the guard:

**What it does**:
1. Kills existing runners
2. Starts first instance with `--loop` (not `--once`)
3. Attempts duplicate `--loop` instance
4. Verifies second instance is blocked in < 5 seconds
5. Confirms exactly 1 runner process remains

**Old script issues** (verify_single_instance.ps1):
- Used `--once` instead of `--loop` (didn't test actual scenario)
- Unicode characters rendered as garbage
- Incomplete loop mode coverage

---

## Changes Made

### `src/app/runner.py`

#### Added Parent Process Detection
```python
def _check_parent_is_runner() -> tuple[bool, dict]:
    """Check if parent is python.exe running runner (re-exec detection)."""
    ppid = os.getppid()
    parent_handle = win32api.OpenProcess(...)
    parent_exe = win32process.GetModuleFileNameEx(parent_handle, 0)
    if parent_name == "python.exe":
        # Query cmdline via WMI, check for runner.py/src.app.runner
        ...
    return is_runner, info_dict
```

#### Early Exit in `if __name__ == "__main__"`
```python
if __name__ == "__main__":
    # EARLY EXIT: Detect re-exec BEFORE guard
    parent_is_runner, parent_info = _check_parent_is_runner()
    if parent_is_runner:
        # Print diagnostics and exit with code 99
        sys.exit(99)

    # ... rest of guard logic ...
```

### `tools/run_paper_dryrun.ps1`

- **Removed**: PowerShell file lock logic (Python guard is authoritative)
- **Improved**: Logging shows python path, module name, working directory
- **Unchanged**: Continues using `-m src.app.runner` (required for imports)

### `tools/verify_single_instance_loop.ps1`

- **New file**: Proper loop mode verification
- **Tests**: Duplicate `--loop` instance is blocked quickly
- **Checks**: Guard message present, fast exit (< 5s), single process

---

## Testing

### Quick Local Test

**Terminal 1** - Start loop:
```powershell
cd C:\dev\ai-trader
.\.venv\Scripts\python.exe -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run
```

**Terminal 2** - Try duplicate (should be blocked immediately):
```powershell
cd C:\dev\ai-trader
.\.venv\Scripts\python.exe -m src.app.runner --mode paper --loop --sleep-seconds 3600 --dry-run
```

**Expected in Terminal 2** (either outcome is success):
- **Scenario A**: "DETECTED RUNNER CHILD PROCESS" message, exit code 99
  - Windows triggered python->python re-exec
  - Parent detection caught the child immediately
  - Child exits before reaching guard logic
- **Scenario B**: "SINGLE INSTANCE GUARD: Another instance is already running", exit code 1
  - No re-exec occurred
  - Mutex/file lock guard blocked the duplicate instance

Both scenarios indicate proper protection. Exit within 1-2 seconds.

### Automated Verification

```powershell
powershell -ExecutionPolicy Bypass -File tools\verify_single_instance_loop.ps1
```

**Expected output**:
```
[PASS] Guard blocked duplicate instance
[PASS] Blocked quickly: X.XXs
[PASS] Exactly 1 runner process running

[VERIFICATION PASSED]
```

### Check Running Processes

```powershell
Get-Process python | Where-Object {
    (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*runner*"
} | Select-Object Id, StartTime, @{Name="CommandLine";Expression={
    (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine
}}
```

**Expected**: Maximum 1 runner process at any time.

---

## Production Impact

### Safe Changes

- **No trading logic modified**: Only guard and launcher updated
- **Backward compatible**: Old launch methods still work (but `-m` not recommended)
- **Fail-closed**: If detection fails, guard still blocks via mutex/file lock
- **Already required dependency**: Uses pywin32 which is already mandatory for Windows

### Benefits

- **Prevents duplicate loops**: Re-exec children exit immediately
- **Clear diagnostics**: Easy to identify when re-exec occurs
- **Reduced re-exec likelihood**: Running runner.py directly is more reliable
- **Better logging**: Scheduler logs show exact paths and working directory

### Notes

- **Exit code 99** is new: Indicates re-exec child detection
- **Scheduler wrapper simplified**: No longer has its own lock (Python guard is source of truth)
- **Verification script updated**: New script properly tests loop mode

---

## Rollback Plan

If issues arise:

```bash
git revert <commit-hash>
```

This will:
- Remove parent process detection
- Restore `-m` module invocation in scheduler
- Restore old PowerShell lock logic
- Remove new verification script

**Note**: Original mutex/file lock guard remains and will still provide protection (though re-exec children may not be caught as early).

---

## Related Files

| File | Purpose |
|------|---------|
| `src/app/runner.py` | Parent detection + early exit logic |
| `tools/run_paper_dryrun.ps1` | Scheduler wrapper (runs runner.py directly) |
| `tools/verify_single_instance_loop.ps1` | Loop mode verification script |
| `WINDOWS_REEXEC_FIX.md` | This documentation |

---

## Commit Message

```
fix: prevent windows runner re-exec causing duplicate loop processes

Problem:
Windows python->python double-launch produces two concurrent loop processes
with identical command lines (parent PID spawning child PID). Existing
mutex/file lock guard ran too late to catch re-exec children.

Solution:
1. Added early parent process detection using pywin32 to identify and
   immediately exit re-exec child processes (exit code 99)
2. Simplified scheduler wrapper (removed PS lock, Python guard authoritative)
3. Created proper loop mode verification script
4. Continue using -m flag (required for imports), but catch re-exec early

Changes:
- src/app/runner.py: Added _check_parent_is_runner() and early exit
- tools/run_paper_dryrun.ps1: Removed PS lock, improved logging
- tools/verify_single_instance_loop.ps1: New verification script

Testing:
- Run tools/verify_single_instance_loop.ps1 to verify guard works
- Monitor Task Scheduler runs for any duplicate processes
- Check logs/task_scheduler.log for runner start/exit events

No trading logic modified. Fail-closed behavior preserved.
```

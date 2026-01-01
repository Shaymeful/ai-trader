# Single Instance Guard - Final Implementation

## Problem Statement

Multiple instances of `src.app.runner` were running concurrently on Windows despite previous guard attempts. This caused:
- Race conditions in state file access
- Duplicate order submissions
- Inconsistent PnL tracking
- Production-critical correctness violations

## Root Cause

Previous implementation issues:
1. Used `ctypes` instead of `pywin32` for mutex (unreliable)
2. Tried `Global\` namespace which can fail due to permissions
3. Had fallback/"continue anyway" logic that allowed execution even when guard failed
4. File lock implementation was not truly exclusive at OS level

## Solution: Fail-Closed Dual Guard

### Design Principles

1. **FAIL-CLOSED**: If guard cannot verify single instance → EXIT immediately
2. **NO FALLBACKS**: No "continue anyway", no silent failures, no best-effort
3. **DUAL MECHANISM**: BOTH mutex AND file lock required
4. **EARLY EXECUTION**: Runs at absolute start of `main()`, before argument parsing
5. **PRODUCTION-CRITICAL**: This is correctness enforcement, not convenience

### Implementation Details

#### Guard #1: Windows Named Mutex (pywin32)

```python
def _acquire_mutex(mutex_name: str) -> bool:
    """Uses win32event.CreateMutex with ERROR_ALREADY_EXISTS check"""
    global _MUTEX_HANDLE

    # Create mutex using pywin32
    _MUTEX_HANDLE = win32event.CreateMutex(None, True, mutex_name)

    # Check if already existed
    if win32api.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return False  # Another instance running

    return True  # Successfully acquired
```

**Key Properties**:
- Mutex name: `Local\AI_TRADER__PAPER_DRYRUN_LOOP` (session-local, reliable)
- Uses `pywin32` library (`win32event.CreateMutex`)
- Checks `ERROR_ALREADY_EXISTS` (183) to detect duplicates
- Handle stored in global `_MUTEX_HANDLE` (held for process lifetime)
- Auto-released by OS when process exits

#### Guard #2: Exclusive File Lock (CreateFileW)

```python
def _acquire_file_lock(lock_file: Path) -> bool:
    """Uses CreateFileW with dwShareMode=0 for true exclusive access"""
    global _LOCK_FILE_HANDLE

    # Windows CreateFileW with no sharing
    handle = windll.kernel32.CreateFileW(
        str(lock_file),
        GENERIC_READ | GENERIC_WRITE,
        0,  # dwShareMode = 0 (NO SHARING - exclusive)
        None,
        OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        None
    )

    if handle == -1:  # INVALID_HANDLE_VALUE
        return False  # Lock held by another process

    _LOCK_FILE_HANDLE = handle
    return True
```

**Key Properties**:
- Lock file: `logs/paper_dryrun.lock`
- OS-level exclusive lock via `CreateFileW` with `dwShareMode=0`
- True exclusive access - no other process can open file while locked
- Handle stored in global `_LOCK_FILE_HANDLE` (held for process lifetime)
- Auto-released by OS when process exits

#### Combined Guard Logic

```python
def _single_instance_guard(mutex_name: str, lock_file: Path) -> bool:
    """BOTH guards must succeed or execution stops"""

    # Guard 1: Mutex
    if not _acquire_mutex(mutex_name):
        return False  # EXIT: Mutex failed

    # Guard 2: File Lock
    if not _acquire_file_lock(lock_file):
        return False  # EXIT: File lock failed

    # BOTH acquired - OK to proceed
    return True
```

**FAIL-CLOSED Policy**:
- If mutex fails (exists OR error) → `return False` → EXIT
- If file lock fails (held OR error) → `return False` → EXIT
- **ONLY** if BOTH succeed → execution continues
- **NO** code path allows execution when guard fails

#### Integration in main()

```python
def main():
    # ========================================================================
    # CRITICAL: SINGLE-INSTANCE GUARD - MUST BE FIRST
    # ========================================================================

    # Debug logging
    pid = os.getpid()
    ppid = os.getppid() if hasattr(os, 'getppid') else 'N/A'
    print(f"[runner] pid={pid} ppid={ppid} argv={sys.argv}", flush=True)

    # Guard runs BEFORE argument parsing, BEFORE any loops
    mutex_name = "Local\\AI_TRADER__PAPER_DRYRUN_LOOP"
    lock_file = Path("logs") / "paper_dryrun.lock"

    if not _single_instance_guard(mutex_name, lock_file):
        print("=" * 80)
        print("SINGLE INSTANCE GUARD: Another instance is already running")
        print("=" * 80)
        print(f"Mutex: {mutex_name}")
        print(f"Lock file: {lock_file}")
        print("Exiting.")
        print("=" * 80)
        sys.exit(0)

    # ========================================================================
    # Guard passed - we are the only instance. Continue normally.
    # ========================================================================

    parser = argparse.ArgumentParser(...)
    # ... rest of main()
```

**Execution Order**:
1. Print debug PID/PPID (identify spawn issues)
2. Run single-instance guard (fail-closed)
3. If guard fails → print message → `sys.exit(0)`
4. If guard succeeds → continue with argument parsing, loops, etc.

## Files Changed

### 1. `src/app/runner.py` (+189 lines, -60 lines, net +129)

**Imports**:
```python
# Add pywin32 imports at top
try:
    import win32event
    import win32api
    import pywintypes
except ImportError:
    win32event = None
    win32api = None
    pywintypes = None
```

**Globals**:
```python
# Global handles to keep locks alive
_MUTEX_HANDLE = None
_LOCK_FILE_HANDLE = None
```

**Functions**:
- `_acquire_mutex(mutex_name: str) -> bool` - NEW (45 lines)
- `_acquire_file_lock(lock_file: Path) -> bool` - NEW (46 lines)
- `_single_instance_guard(mutex_name: str, lock_file: Path) -> bool` - REPLACED (33 lines)
- `main()` - UPDATED (guard section rewritten)

**Key Changes**:
- Replaced ctypes with pywin32
- Changed from `Global\` to `Local\` namespace
- Removed all fallback logic
- Implemented true OS-level file lock with `CreateFileW`
- Added debug PID/PPID logging
- Made guard fail-closed (no "continue anyway")

### 2. `requirements.txt` (+3 lines)

```python
# Windows single-instance guard (Windows only)
pywin32>=311; sys_platform == 'win32'
```

**Rationale**: pywin32 now required for production correctness on Windows

### 3. `docs/ARCHITECTURE.md` (+25 lines, -12 lines, net +13)

**Updated Section**: "Process Control > Single Instance Guard"

**Key Updates**:
- Documented pywin32 requirement
- Changed mutex name from `Global\` to `Local\`
- Clarified FAIL-CLOSED policy
- Removed fallback language
- Added dependency note
- Updated verification examples

### 4. `tools/verify_single_instance.ps1` - NEW (150 lines)

Quick verification script that:
1. Checks pywin32 installation
2. Kills existing runners
3. Removes lock files
4. Starts first instance
5. Attempts duplicate (should block in < 5s)
6. Verifies process count = 1
7. Reports PASS/FAIL with color-coded output

## Testing

### Prerequisites

1. Install pywin32:
   ```powershell
   .venv\Scripts\pip.exe install pywin32
   ```

2. Kill existing runners:
   ```powershell
   Get-Process python | Where-Object {
       (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*src.app.runner*"
   } | Stop-Process -Force
   ```

3. Remove lock files:
   ```powershell
   Remove-Item C:\dev\ai-trader\logs\*.lock -Force -ErrorAction SilentlyContinue
   ```

### Automated Test (Recommended)

```powershell
cd C:\dev\ai-trader
.\tools\verify_single_instance.ps1
```

**Expected Output**:
```
================================================================================
Single Instance Guard Verification
================================================================================

[1/5] Checking pywin32 installation...
  ✓ pywin32 installed

[2/5] Cleaning up existing runners...
  No existing runners

[3/5] Removing lock files...
  ✓ Lock files cleared

[4/5] Starting first runner instance...
  Started PID: 12345

[5/5] Attempting duplicate instance (should be BLOCKED)...

Second instance output:
--------------------------------------------------------------------------------
[runner] pid=12346 ppid=12347 argv=[...]
================================================================================
SINGLE INSTANCE GUARD: Another instance is already running
================================================================================
Mutex: Local\AI_TRADER__PAPER_DRYRUN_LOOP
Lock file: logs\paper_dryrun.lock
Exiting.
================================================================================
--------------------------------------------------------------------------------

================================================================================
Results
================================================================================
✓ Guard blocked duplicate instance
✓ Blocked quickly: 0.85s
✓ Exactly 1 runner process exists

================================================================================
✓ VERIFICATION PASSED
================================================================================
```

### Manual Test

**Terminal 1**:
```powershell
cd C:\dev\ai-trader
.\.venv\Scripts\python.exe -m src.app.runner --mode paper --once --dry-run
```

**Terminal 2** (within 5 seconds):
```powershell
cd C:\dev\ai-trader
.\.venv\Scripts\python.exe -m src.app.runner --mode paper --once --dry-run
```

**Expected in Terminal 2**:
```
[runner] pid=12346 ppid=12347 argv=[...]
================================================================================
SINGLE INSTANCE GUARD: Another instance is already running
================================================================================
Mutex: Local\AI_TRADER__PAPER_DRYRUN_LOOP
Lock file: logs\paper_dryrun.lock
Exiting.
================================================================================
```

**Verify process count**:
```powershell
Get-Process python | Where-Object {
    (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*src.app.runner*"
}
```

Should show **exactly 1 process**.

## Success Criteria

✅ **PASS** if ALL of the following are true:

1. **Duplicate blocked**: Second instance prints "SINGLE INSTANCE GUARD" and exits
2. **Fast-fail**: Second instance exits in < 5 seconds (blocked before heavy work)
3. **Single process**: Only ONE runner process exists after all attempts
4. **Debug visible**: `[runner] pid=... ppid=...` printed for each attempt
5. **No JSONL output**: Second instance produces no log files or state changes

❌ **FAIL** if ANY of the following are true:

1. Two or more runner processes running simultaneously
2. Second instance runs normally (no guard message)
3. Second instance takes > 5 seconds to exit
4. Guard failures are silent (no error messages)
5. Execution continues despite guard failure

## Production Deployment

### Installation

```bash
# 1. Update repository
git pull

# 2. Install dependencies
.venv\Scripts\pip.exe install -r requirements.txt

# 3. Verify pywin32
.venv\Scripts\python.exe -c "import win32event; print('OK')"

# 4. Test guard
.\tools\verify_single_instance.ps1
```

### Task Scheduler Integration

The guard works seamlessly with Task Scheduler:

1. Task Scheduler setting: `IfAlreadyRunning: IgnoreNew`
2. PowerShell script lock: `tools/run_paper_dryrun.ps1` (unchanged)
3. Python guard: `src/app/runner.py` (NEW fail-closed implementation)

**Three layers of protection**:
- Layer 1: Task Scheduler prevents overlapping triggers
- Layer 2: PowerShell script holds exclusive file lock
- Layer 3: Python runner enforces mutex + file lock

Even if Task Scheduler or PowerShell fails, Python guard will block duplicates.

### Monitoring

Check logs for blocked attempts:
```powershell
# Check if duplicates were blocked
Get-Content logs\task_scheduler.log -Tail 20 | Select-String "BLOCKED"

# Check for process spawn anomalies
Get-Content logs\task_scheduler.log | Select-String "pid="
```

## Troubleshooting

### "pywin32 not installed"

```powershell
.venv\Scripts\pip.exe install pywin32
```

### "Both mechanisms failed"

- Check `logs/` directory exists and is writable
- Verify not running as restricted user
- Try running PowerShell as Administrator
- Check Windows Event Viewer for application errors

### Two processes still running

1. Check debug logs for PID/PPID relationships:
   ```powershell
   Get-Content logs\verify_instance1.log | Select-String "pid="
   ```

2. Verify guard is being invoked:
   ```powershell
   Get-Content logs\verify_instance1.log | Select-String "GUARD"
   ```

3. Check that pywin32 is installed in correct venv:
   ```powershell
   .venv\Scripts\pip.exe list | Select-String "pywin32"
   ```

### Lock file can't be removed

This is **expected behavior** - lock is held by running process.

Kill the process first:
```powershell
# Find runner PIDs
Get-Process python | Where-Object {
    (Get-WmiObject Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*src.app.runner*"
}

# Kill specific PID
taskkill /F /PID <PID>

# Then remove lock
Remove-Item logs\paper_dryrun.lock -Force
```

## Performance Impact

- **Mutex check**: < 1ms (kernel syscall)
- **File lock**: < 10ms (filesystem operation)
- **Total startup overhead**: < 20ms
- **Runtime impact**: ZERO (checks only at process start)

## Security Considerations

- **Mutex**: `Local\` namespace is session-local (no cross-user access)
- **File lock**: Respects filesystem permissions on `logs/` directory
- **No credentials**: No sensitive data in mutex names or lock files
- **Fail-closed**: Conservative policy prevents unauthorized execution

## Unified Diff Summary

**src/app/runner.py**:
- Added pywin32 imports
- Added global handles `_MUTEX_HANDLE`, `_LOCK_FILE_HANDLE`
- Replaced `_single_instance_guard()` with three functions:
  - `_acquire_mutex()` - pywin32-based mutex
  - `_acquire_file_lock()` - CreateFileW-based exclusive lock
  - `_single_instance_guard()` - fail-closed combiner
- Updated `main()`:
  - Added PID/PPID debug logging
  - Changed mutex name to `Local\`
  - Changed lock file to match PowerShell script
  - Made guard fail-closed (no fallbacks)

**requirements.txt**:
- Added `pywin32>=311; sys_platform == 'win32'`

**docs/ARCHITECTURE.md**:
- Updated "Process Control" section
- Documented pywin32 requirement
- Clarified fail-closed policy
- Updated verification examples

**tools/verify_single_instance.ps1**:
- NEW: Automated verification script
- Tests all guard functionality
- Color-coded PASS/FAIL output

## Conclusion

This implementation provides **production-grade single-instance enforcement** with:

✅ **Correctness**: Fail-closed policy ensures no duplicate execution
✅ **Reliability**: Dual mechanism (mutex + file lock) for defense in depth
✅ **Observability**: Debug logging shows PID/PPID for spawn detection
✅ **Testability**: Automated verification script confirms behavior
✅ **Documentation**: Comprehensive docs for deployment and troubleshooting

**No fallbacks. No silent failures. No "continue anyway".**

This is production-critical correctness enforcement.

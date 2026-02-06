# Dashboard Restart Instructions

## Current Status

The trigger button feature code has been:
- ✅ Committed to repository (commit fb9b9d9)
- ✅ Verified in Python imports (endpoint exists when importing app directly)
- ✅ Tested during development (worked correctly)

However, the dashboard currently running on **port 8000 (PID 69476)** was started **before** the code changes were committed, so it doesn't have the new trigger endpoint.

---

## Why Restart is Needed

The dashboard on port 8000 is running an older version of the code (from before commit fb9b9d9). To load the new trigger endpoint, you need to restart the dashboard process.

---

## How to Restart the Dashboard

### Option 1: Manual Restart (Recommended)

1. **Stop the current dashboard:**
   ```powershell
   # Find and stop the process
   taskkill /F /PID 69476
   ```

2. **Start the new dashboard:**
   ```powershell
   cd C:\dev\ai-trader
   .venv\Scripts\python.exe -m uvicorn src.ui_api.app:app --host 0.0.0.0 --port 8000
   ```

3. **Access the dashboard:**
   ```
   http://localhost:8000
   ```

4. **Verify trigger endpoint:**
   ```powershell
   curl -X POST http://localhost:8000/runtime/trigger_loop -H "Content-Type: application/json"
   ```

   Should return:
   ```json
   {
       "success": true,
       "message": "Loop trigger sent. Next iteration will start within 5 seconds.",
       "pending_version": null
   }
   ```

---

### Option 2: Using the Start Script

Use the existing startup script:

```powershell
cd C:\dev\ai-trader
.\tools\windows\start_dashboard.ps1
```

This will handle starting the dashboard with the latest code.

---

### Option 3: Use Port 8001 Temporarily

If you can't stop the process on port 8000, you can use the dashboard on a different port:

1. **Start dashboard on port 8001:**
   ```powershell
   cd C:\dev\ai-trader
   .venv\Scripts\python.exe -c "
   import sys
   sys.path.insert(0, '.')
   from src.ui_api.app import app
   import uvicorn
   print('Starting dashboard on port 8001...')
   uvicorn.run(app, host='0.0.0.0', port=8001)
   "
   ```

2. **Access at:**
   ```
   http://localhost:8001
   ```

**Note:** This approach imports the app module directly in Python, which ensures the latest code is loaded.

---

## Verification Steps

After restarting, verify the trigger button is working:

### 1. Check Health Endpoint
```bash
curl http://localhost:8000/health
```

### 2. Check Runtime State
```bash
curl http://localhost:8000/runtime
```

### 3. Test Trigger Endpoint
```bash
curl -X POST http://localhost:8000/runtime/trigger_loop -H "Content-Type: application/json"
```

Expected response:
```json
{
    "success": true,
    "message": "Loop trigger sent. Next iteration will start within 5 seconds.",
    "pending_version": null
}
```

### 4. Check Dashboard UI
1. Open `http://localhost:8000` in browser
2. Navigate to "Loop Status" section
3. Verify "⚡ Trigger Now" button is visible
4. Click button and verify success message

---

## Troubleshooting

### Issue: "Port already in use"
**Solution:** The old dashboard is still running. Stop it first with `taskkill /F /PID 69476`

### Issue: "Trigger endpoint returns 404 Not Found"
**Solution:** The dashboard hasn't loaded the new code. Try:
1. Clear Python cache: `find src/ui_api -name "*.pyc" -delete`
2. Restart dashboard using Option 3 (direct Python import)

### Issue: "Access is denied" when using taskkill
**Solution:**
1. Run PowerShell as Administrator, OR
2. Use Option 3 to start on port 8001 instead

---

## What the Trigger Button Does

Once the dashboard is restarted:

1. **User clicks "⚡ Trigger Now"** in Loop Status section
2. **API creates trigger flag** at `state/trigger_loop.flag`
3. **Runner checks flag** every 5 seconds during sleep
4. **Runner wakes up** within 5 seconds and starts next iteration immediately
5. **Flag automatically deleted** after triggering

---

## Monday Morning Checklist

Before markets open:

- [ ] Restart dashboard to load trigger button
- [ ] Verify trigger endpoint responds correctly
- [ ] Open dashboard in browser and confirm button is visible
- [ ] Test trigger button once to verify runner wakes up
- [ ] Monitor first loop iteration after trigger

---

## Additional Notes

- **No impact on runner:** The runner already has the latest code (running from commit fb9b9d9)
- **No trading impact:** Trigger mechanism is independent of trading logic
- **Safe to test:** Trigger button can be tested anytime without affecting current operations
- **Automatic cleanup:** Trigger flags are automatically deleted, no manual cleanup needed

---

## Questions?

If you encounter any issues:

1. Check `logs/loop_status.log` for runner activity
2. Check dashboard console output for errors
3. Verify code is committed: `git log -1 --oneline` should show commit fb9b9d9
4. Verify trigger code exists: `grep -n "trigger_loop" src/ui_api/app.py`


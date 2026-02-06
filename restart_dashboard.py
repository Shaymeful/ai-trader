"""Restart dashboard with fresh code load."""
import os
import sys

# Ensure we're in the right directory
os.chdir(r'C:\dev\ai-trader')
sys.path.insert(0, os.getcwd())

# Clear any cached modules
modules_to_clear = [m for m in sys.modules.keys() if m.startswith('src.ui_api')]
for mod in modules_to_clear:
    del sys.modules[mod]

# Now import fresh
from src.ui_api.app import app
import uvicorn

# Verify trigger endpoint exists
routes = [r.path for r in app.routes if hasattr(r, 'path')]
if '/runtime/trigger_loop' in routes:
    print("[OK] Trigger endpoint found in routes")
else:
    print("[WARNING] Trigger endpoint NOT found!")
    print(f"Runtime routes: {[r for r in routes if 'runtime' in r]}")

print("\n" + "=" * 60)
print("Starting AI Trader Dashboard on port 8001")
print("=" * 60)
print(f"Dashboard: http://localhost:8001")
print(f"API Docs:  http://localhost:8001/docs")
print(f"Health:    http://localhost:8001/health")
print("")
print("Endpoints available:")
print("  POST /runtime/trigger_loop    - Trigger immediate loop")
print("  POST /runtime/loop_interval   - Update loop interval")
print("  GET  /runtime                 - Get runtime state")
print("=" * 60)
print("")

uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")

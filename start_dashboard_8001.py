"""Start dashboard on port 8001 with trigger endpoint."""
import sys
sys.path.insert(0, '.')

from src.ui_api.app import app
import uvicorn

if __name__ == "__main__":
    print("Starting AI Trader Dashboard on port 8001...")
    print("Access at: http://localhost:8001")
    print("Trigger endpoint: POST /runtime/trigger_loop")
    print("")
    uvicorn.run(app, host="0.0.0.0", port=8001)

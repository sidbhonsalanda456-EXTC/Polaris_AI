import os
import sys
import time
import webbrowser
import threading
import uvicorn

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def open_browser(url: str, delay_seconds: float = 1.5):
    """Opens the user's default browser after the server has initialized."""
    time.sleep(delay_seconds)
    print(f"\n[Browser] Opening Mission Control Dashboard at {url} ...")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"[Browser] Could not auto-open browser ({e}). Please manually open: {url}")

def main():
    host = "127.0.0.1"
    port = 8000
    url = f"http://{host}:{port}"

    print("=" * 75)
    print("  SIH26061: AI-Driven Smart Energy Management for Polar Research Stations")
    print("  Station Aurora-01 • Autonomous Microgrid Mission Control Center")
    print("=" * 75)
    print(f"\n[1/2] Initializing Simulation Coordinator, Digital Twin & PPO Agent...")
    print(f"[2/2] Launching Web Server on {url} ...")
    print(f"      - Dashboard: {url}")
    print(f"      - REST API:  {url}/api/status")
    print(f"      - WebSocket: ws://{host}:{port}/ws/telemetry")
    print("\nPress CTRL+C at any time to stop the application.\n")

    # Launch browser in a background timer thread
    threading.Thread(target=open_browser, args=(url, 1.5), daemon=True).start()

    # Run Uvicorn server directly with FastAPI app
    try:
        from backend.main import app
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except KeyboardInterrupt:
        print("\n[Shutdown] Stopping Station Aurora-01 Mission Control cleanly. Goodbye!")
    except Exception as e:
        print(f"\n[Error] Server encountered an error: {e}")

if __name__ == "__main__":
    main()

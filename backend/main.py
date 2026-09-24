import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Ensure root directory is on Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.api.routes import router as api_router
from backend.services.station_service import coordinator

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start coordinator background simulation loop
    coordinator.start()
    print("[Backend] Polar Research Station coordinator loop initialized.")
    yield
    # Shutdown: stop coordinator
    coordinator.stop()
    print("[Backend] Coordinator loop cleanly shutdown.")

app = FastAPI(
    title="SIH260061 Polar Station Energy Management System",
    description="Autonomous AI-driven Energy Management for Polar Research Stations",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include REST routes
app.include_router(api_router)

# Mount Prachi's IoT & Admin Backend routes directly on root /
PRACHI_BACKEND_DIR = os.path.join(PROJECT_ROOT, "team_modules", "backend_prachi", "backend")
if os.path.exists(PRACHI_BACKEND_DIR) and PRACHI_BACKEND_DIR not in sys.path:
    sys.path.insert(0, PRACHI_BACKEND_DIR)
try:
    from app.main import app as prachi_app
    app.mount("/backend-api", prachi_app)
    # Also include the core router endpoints directly at root for POLARIS UI compatibility
    for route in prachi_app.routes:
        # Skip doc routes
        if getattr(route, "path", "").startswith(("/docs", "/openapi", "/redoc")):
            continue
        app.router.routes.append(route)
    print("[Backend] Prachi's IoT & Admin routes integrated successfully.")
except Exception as e:
    print("[Backend] Note: Prachi app integration warning:", e)

# WebSocket endpoint for real-time telemetry
@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    coordinator.telemetry_clients.add(websocket)
    try:
        # Send initial state immediately upon connection
        await websocket.send_json({
            "type": "initial_state",
            "data": coordinator.latest_telemetry,
            "twin": coordinator.digital_twin.get_ditto_model()
        })
        while True:
            # Keep socket alive and receive any client-side commands
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        coordinator.telemetry_clients.discard(websocket)

# WebSocket endpoint for real-time training progress
@app.websocket("/ws/training")
async def websocket_training(websocket: WebSocket):
    await websocket.accept()
    coordinator.training_clients.add(websocket)
    try:
        await websocket.send_json({
            "type": "training_state",
            "data": coordinator.ai_trainer.get_stats()
        })
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        coordinator.training_clients.discard(websocket)

# Mount dashboard static files
DASHBOARD_DIR = os.path.join(PROJECT_ROOT, "dashboard")
POLARIS_DIR = os.path.join(DASHBOARD_DIR, "polaris")
if os.path.exists(DASHBOARD_DIR):
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR), name="static")
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR), name="dashboard")

    @app.get("/")
    def serve_dashboard():
        polaris_index = os.path.join(POLARIS_DIR, "index.html")
        if os.path.exists(polaris_index):
            return FileResponse(polaris_index)
        return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))

    @app.get("/telemetry")
    def serve_detailed_telemetry():
        index_file = os.path.join(DASHBOARD_DIR, "index.html")
        return FileResponse(index_file)

    @app.get("/polaris")
    def serve_polaris_home():
        polaris_index = os.path.join(POLARIS_DIR, "index.html")
        if os.path.exists(polaris_index):
            return FileResponse(polaris_index)
        return FileResponse(os.path.join(DASHBOARD_DIR, "index.html"))

    @app.get("/{page_name}.html")
    def serve_polaris_html_page(page_name: str):
        # Check polaris directory first
        p_file = os.path.join(POLARIS_DIR, f"{page_name}.html")
        if os.path.exists(p_file):
            return FileResponse(p_file)
        # Check root dashboard directory
        d_file = os.path.join(DASHBOARD_DIR, f"{page_name}.html")
        if os.path.exists(d_file):
            return FileResponse(d_file)
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Page {page_name}.html not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)

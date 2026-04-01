from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import uvicorn

# --- 1. IMPORT ROUTER ---
from anchor import rp_router

app = FastAPI()

# --- 2. CORS (For React Dev Server) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. STATIC FILES ---
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# --- 4. API ROUTER ---
app.include_router(rp_router.router)

# --- 5. SERVE REACT BUILD (Production) ---
REACT_BUILD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
REACT_STATIC_DIR = os.path.join(REACT_BUILD_DIR, "static")

# Mount React's static bundles (JS/CSS) at /static/
if os.path.exists(REACT_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=REACT_STATIC_DIR), name="react-static")

@app.get("/")
def serve_root():
    index_path = os.path.join(REACT_BUILD_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return HTMLResponse(
        "<html><body style='background:#0f172a;color:#e2e8f0;font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh'>"
        "<div style='text-align:center'><h1>RMIX</h1><p>Frontend not built yet. Run: <code>cd frontend && npm run build</code></p></div>"
        "</body></html>"
    )

# --- 6. SPA CATCH-ALL (Must be LAST) ---
@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    # 1. Try serving from React build directory
    static_path = os.path.join(REACT_BUILD_DIR, full_path)
    if os.path.exists(static_path) and os.path.isfile(static_path):
        return FileResponse(static_path)
    
    # 2. SPA fallback: return index.html for client-side routing
    index_path = os.path.join(REACT_BUILD_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    
    return {"error": f"Not found: '{full_path}'"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
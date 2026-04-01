"""
RMIX Desktop Launcher
Starts FastAPI backend + opens a native window using pywebview.
"""
import sys
import os
import threading
import time
import socket

# Ensure root directory in path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def is_port_open(port, host="127.0.0.1", timeout=0.5):
    """Check if a port is already in use or ready."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, socket.timeout, OSError):
        return False


def start_server():
    """Start the FastAPI/Uvicorn server in a thread."""
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )


def wait_for_server(port=8000, retries=30, delay=0.5):
    """Wait until the server is responding."""
    for _ in range(retries):
        if is_port_open(port):
            return True
        time.sleep(delay)
    return False


def main():
    try:
        import webview
    except ImportError:
        print("[ERROR] pywebview not installed. Installing...")
        os.system(f"{sys.executable} -m pip install pywebview")
        import webview

    print("[RMIX] Starting server...")
    
    # Start server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    print("[RMIX] Waiting for server to start...")
    if not wait_for_server():
        print("[ERROR] Server failed to start!")
        return

    print("[RMIX] Server ready! Opening application window...")
    
    # Create native window
    # Append timestamp to bypass aggressive WebView HTML caching
    window = webview.create_window(
        title="RMIX",
        url=f"http://127.0.0.1:8000?v={int(time.time())}",
        width=1400,
        height=860,
        min_size=(900, 600),
        background_color="#0f172a",
        text_select=True,
    )

    # Start the GUI event loop (blocks until window is closed)
    webview.start(
        debug=False,
        http_server=False,
        private_mode=False
    )

    print("[RMIX] Window closed. Shutting down...")


if __name__ == "__main__":
    main()

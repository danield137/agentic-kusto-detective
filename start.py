"""Start the Kusto Detective Dashboard (backend + frontend)."""

import subprocess
import sys
import time


def main():
    print("🚀 Starting Kusto Detective Dashboard...\n")

    # Start FastAPI backend
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "detective.server:app",
         "--host", "127.0.0.1", "--port", "8080"],
    )
    print("  ✅ Backend:  http://127.0.0.1:8080")

    # Start Vite dev server
    frontend = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd="web",
        shell=True,
    )
    print("  ✅ Frontend: http://localhost:5173")
    print("\n  Open http://localhost:5173 in your browser.")
    print("  Press Ctrl+C to stop.\n")

    try:
        while True:
            if backend.poll() is not None:
                print("Backend exited.")
                break
            if frontend.poll() is not None:
                print("Frontend exited.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        backend.terminate()
        frontend.terminate()
        backend.wait()
        frontend.wait()
        print("Done.")


if __name__ == "__main__":
    main()

"""
Launcher for Smart Meter Analysis Hub.
Ensures only a single Streamlit instance is started for `Home.py` by checking the port and using a lock file.
"""
from __future__ import annotations

import sys
import os
import subprocess
import tempfile
import time
import webbrowser
from pathlib import Path
import socket
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("run_app")

HOME_PY = Path(__file__).with_name("Home.py")
LOCK_FILE = Path(tempfile.gettempdir()) / "smartmeter_home_streamlit.lock"
PORT = 8501
HOST = "127.0.0.1"


def port_open(host: str = HOST, port: int = PORT, timeout: float = 0.8) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except Exception:
        return False
    return True


def main() -> int:
    if port_open():
        print(f"Streamlit appears to be already running. Open http://{HOST}:{PORT} in your browser.")
        return 0

    if LOCK_FILE.exists():
        try:
            existing_pid = int(LOCK_FILE.read_text())
            if is_pid_alive(existing_pid):
                # Give it a brief moment to start responding
                for _ in range(6):
                    if port_open():
                        print(f"Streamlit appears to be already running (PID={existing_pid}). Open http://{HOST}:{PORT} in your browser.")
                        return 0
                    time.sleep(0.5)
                print("Found existing launcher process but server not responding. Removing stale lock and continuing.")
                try:
                    LOCK_FILE.unlink()
                except Exception:
                    pass
            else:
                try:
                    LOCK_FILE.unlink()
                except Exception:
                    pass
        except Exception:
            try:
                LOCK_FILE.unlink()
            except Exception:
                pass

    cmd = [sys.executable, "-m", "streamlit", "run", str(HOME_PY), "--server.headless", "true"]

    try:
        proc = subprocess.Popen(cmd, cwd=str(HOME_PY.parent))
    except Exception as e:
        logger.error("Failed to start Streamlit: %s", e)
        print("Start the app manually with: streamlit run Home.py")
        return 1

    # Wait for server to be ready
    started = False
    for _ in range(30):
        if port_open():
            started = True
            break
        time.sleep(0.5)

    # Write lock file
    try:
        LOCK_FILE.write_text(str(proc.pid))
    except Exception:
        logger.debug("Unable to write lock file for Streamlit launcher.")

    if started:
        try:
            webbrowser.open_new_tab(f"http://{HOST}:{PORT}")
        except Exception:
            pass
        print(f"Streamlit launched and reachable at http://{HOST}:{PORT}")
    else:
        print("Streamlit launched but did not respond within timeout. Check logs or run: streamlit run Home.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

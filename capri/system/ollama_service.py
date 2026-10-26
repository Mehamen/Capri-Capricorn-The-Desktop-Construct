"""
ollama_service.py
Makes sure Ollama is running when Capri starts (useful at Windows startup,
when Capri may launch before Ollama is up).
"""

import os
import shutil
import subprocess
import threading
import time
import urllib.request

TAGS_URL = "http://localhost:11434/api/tags"


def is_running() -> bool:
    try:
        with urllib.request.urlopen(TAGS_URL, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _find_launch_command():
    local = os.environ.get("LOCALAPPDATA", "")
    tray_app = os.path.join(local, "Programs", "Ollama", "ollama app.exe")
    if os.path.exists(tray_app):
        return [tray_app]                    # tray app starts the server itself
    exe = shutil.which("ollama") or os.path.join(local, "Programs", "Ollama", "ollama.exe")
    if os.path.exists(exe):
        return [exe, "serve"]
    return None


def start() -> bool:
    cmd = _find_launch_command()
    if not cmd:
        print("[Ollama] Not found — install it from https://ollama.com")
        return False
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen(cmd, creationflags=flags,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def ensure_running_async(timeout_s: int = 90) -> None:
    """Non-blocking: start Ollama if needed and wait for it in background."""
    def _worker():
        if is_running():
            print("[Ollama] Already running.")
            return
        print("[Ollama] Not running — starting it...")
        if not start():
            return
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if is_running():
                print("[Ollama] Ready.")
                return
            time.sleep(2)
        print("[Ollama] Did not come up in time.")
    threading.Thread(target=_worker, daemon=True).start()

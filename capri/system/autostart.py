"""
autostart.py
Turns "start Capri with Windows" on/off.

Uses the per-user Run key in the registry:
    HKCU\Software\Microsoft\Windows\CurrentVersion\Run
No admin rights needed. Launches run_capri.pyw via pythonw.exe,
so no console window appears.
"""

import sys
from pathlib import Path

RUN_KEY    = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Capri"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER     = PROJECT_ROOT / "run_capri.pyw"

try:
    import winreg
except ImportError:          # not Windows — feature just stays off
    winreg = None


def is_supported() -> bool:
    return winreg is not None


def _pythonw() -> str:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.exists() else exe)


def _command() -> str:
    return f'"{_pythonw()}" "{LAUNCHER}"'


def is_enabled() -> bool:
    if not winreg:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def enable() -> None:
    if not winreg:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())


def disable() -> None:
    if not winreg:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass


def set_enabled(on: bool) -> None:
    enable() if on else disable()

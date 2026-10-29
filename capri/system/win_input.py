"""
win_input.py
Tiny Windows helpers (ctypes only, no extra packages):
  - press keys / media keys, type any text (incl. Cyrillic, any keyboard layout)
  - find a program's window by its .exe name, read its title
  - bring a window to the front and back
"""

import ctypes
import os
import time
from ctypes import wintypes

IS_WINDOWS = os.name == "nt"

# virtual-key codes
VK_BACK, VK_TAB, VK_RETURN, VK_SHIFT, VK_CONTROL, VK_MENU, VK_ESCAPE = 0x08, 0x09, 0x0D, 0x10, 0x11, 0x12, 0x1B
VK_VOLUME_MUTE, VK_VOLUME_DOWN, VK_VOLUME_UP = 0xAD, 0xAE, 0xAF
VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_STOP, VK_MEDIA_PLAY_PAUSE = 0xB0, 0xB1, 0xB2, 0xB3
EXTENDED = {VK_VOLUME_MUTE, VK_VOLUME_DOWN, VK_VOLUME_UP,
            VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_STOP, VK_MEDIA_PLAY_PAUSE}


def vk_letter(ch: str) -> int:
    """'K' → its virtual-key code (letters / digits)."""
    return ord(ch.upper())


if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ULONG_PTR = ctypes.c_size_t

    INPUT_KEYBOARD = 1
    KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x1, 0x2, 0x4

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _send(inputs):
        arr = (INPUT * len(inputs))(*inputs)
        user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))

    def _key(vk: int, up: bool) -> "INPUT":
        flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0)
        return INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags,
                                                         time=0, dwExtraInfo=0))

    def press(*vks: int) -> None:
        """press(VK_CONTROL, vk_letter('K')) = Ctrl+K"""
        _send([_key(v, False) for v in vks] + [_key(v, True) for v in reversed(vks)])

    def tap(vk: int, times: int = 1, delay: float = 0.0) -> None:
        for _ in range(times):
            press(vk)
            if delay:
                time.sleep(delay)

    def type_text(text: str) -> None:
        """Types text as Unicode — works with any keyboard layout."""
        inputs = []
        raw = text.encode("utf-16-le")
        for i in range(0, len(raw), 2):
            code = raw[i] | (raw[i + 1] << 8)
            for up in (False, True):
                inputs.append(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(
                    wVk=0, wScan=code,
                    dwFlags=KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0),
                    time=0, dwExtraInfo=0)))
        _send(inputs)

    def _exe_of(hwnd) -> str:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x1000, False, pid.value)   # QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
            return ""
        finally:
            kernel32.CloseHandle(h)

    def title_of(hwnd) -> str:
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def windows_of(exe: str) -> list:
        """All top-level windows with a title that belong to e.g. 'spotify.exe'."""
        exe = exe.lower()
        found = []

        @WNDENUMPROC
        def cb(hwnd, _):
            if user32.GetWindowTextLengthW(hwnd) > 0 and _exe_of(hwnd) == exe:
                found.append(hwnd)
            return True

        user32.EnumWindows(cb, 0)
        return found

    def foreground():
        return user32.GetForegroundWindow()

    def focus(hwnd) -> bool:
        """Bring a window to the front (works around Windows' focus-stealing lock)."""
        if not hwnd:
            return False
        if user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        for attempt in range(3):
            press(VK_MENU)                       # lets us take the focus
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.15)
            if user32.GetForegroundWindow() == hwnd:
                return True
            # second trick: share input with the current foreground thread
            fg = user32.GetForegroundWindow()
            a = user32.GetWindowThreadProcessId(fg, None)
            b = kernel32.GetCurrentThreadId()
            user32.AttachThreadInput(b, a, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(b, a, False)
            time.sleep(0.15)
            if user32.GetForegroundWindow() == hwnd:
                return True
        return False

else:   # not Windows — everything is a no-op so the app still runs
    def press(*vks): pass
    def tap(vk, times=1, delay=0.0): pass
    def type_text(text): pass
    def title_of(hwnd): return ""
    def windows_of(exe): return []
    def foreground(): return None
    def focus(hwnd): return False

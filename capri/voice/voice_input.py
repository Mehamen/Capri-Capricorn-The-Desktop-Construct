"""
voice_input.py
Glue between the microphone side and the UI:

  «Капри» (Vosk, cheap) → Whisper confirms it → "listening…"
  → command recorded → Whisper turns it into text → sent to the chat.

All heavy work runs in a background thread; results reach the UI
through Qt signals.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from capri.voice.transcriber import Transcriber
from capri.voice.wake_word import WakeWordListener


class VoiceInput(QObject):
    listening  = Signal()       # it really was «Капри» — show "listening"
    processing = Signal()       # command recorded, turning it into text
    heard      = Signal(str)    # the command as text
    nothing    = Signal()       # «Капри» but no command after it
    info       = Signal(str)    # status line for the chat

    def __init__(self, enabled: bool = True):
        super().__init__()
        self.stt = Transcriber()
        self.listener = WakeWordListener(
            on_trigger=self._on_trigger,
            on_command=self._on_command,
        )
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voice")
        self._confirm = None
        self.listener.start(enabled)

    # ── called from the audio thread ─────────────────────────────────

    def _on_trigger(self, audio) -> None:
        self._confirm = self._pool.submit(self._confirm_wake, audio)

    def _on_command(self, audio) -> None:
        self._pool.submit(self._finish, self._confirm, audio)
        self._confirm = None

    # ── worker thread ────────────────────────────────────────────────

    def _confirm_wake(self, audio) -> bool:
        if not self.stt.ready.is_set():
            # Whisper still loading — don't queue up old commands
            self.listener.cancel_command("Whisper still loading")
            self.info.emit("🎙 распознавание речи ещё загружается — попробуй через минуту")
            return False
        t0 = time.monotonic()
        ok, text = self.stt.confirm_wake(audio)
        print(f"[Wake] Whisper heard {text!r} → {'yes' if ok else 'no'} "
              f"({time.monotonic() - t0:.2f}s)")
        if ok:
            self.listening.emit()
        else:
            self.listener.cancel_command("not «Капри»")
        return ok

    def _finish(self, confirm, audio) -> None:
        if confirm is not None and not confirm.result():
            return
        self.processing.emit()
        t0 = time.monotonic()
        text = self.stt.transcribe(audio)
        found, command = Transcriber.split_command(text)
        if not found:
            command = text.strip()
        print(f"[STT] {text!r} → command {command!r} "
              f"({time.monotonic() - t0:.2f}s, {self.stt.device})")
        if command:
            self.heard.emit(command)
        else:
            self.nothing.emit()

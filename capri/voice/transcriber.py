"""
transcriber.py
Whisper speech-to-text for voice commands (Russian).

- Uses the GPU when possible (fast, CPU stays free), otherwise the CPU.
- Also double-checks the wake word: Vosk is cheap but sometimes hears
  «Капри» in «капитан» / «паприка»; Whisper confirms it really was her name.

GPU needs NVIDIA's CUDA libraries once:
    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*
Without them Capri simply uses the CPU (slower, still works).
"""

import difflib
import glob
import os
import re
import sys
import threading
from typing import Callable

from pathlib import Path

import numpy as np

# ── tuneable ─────────────────────────────────────────────────────────
GPU_MODEL   = "large-v3-turbo"   # ~1.6 GB download once, very good Russian
CPU_MODEL   = "small"            # fallback, ~0.5 GB
LANGUAGE    = "ru"
WAKE_FORMS  = ["капри", "capri"]
# Whisper sometimes "hears" these in silence — ignore them
HALLUCINATIONS = [
    "продолжение следует", "субтитры", "dimatorzok", "спасибо за просмотр",
    "редактор субтитров", "подписывайтесь",
]
# ─────────────────────────────────────────────────────────────────────


MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


def _model_source(name: str) -> str:
    """Use models/faster-whisper-<name> if it was downloaded there, else download by name."""
    local = MODELS_DIR / f"faster-whisper-{name}"
    return str(local) if (local / "model.bin").exists() else name


def _add_cuda_dll_dirs() -> None:
    """Make pip-installed NVIDIA DLLs (nvidia-cublas/cudnn) findable on Windows."""
    if os.name != "nt":
        return
    for sp in {p for p in sys.path if p.rstrip("\\/").endswith("site-packages")}:
        for b in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(b)
            except OSError:
                pass
            os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")


def _dll_found(name: str) -> bool:
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d and os.path.exists(os.path.join(d, name)):
            return True
    return False


def _gpu_ready() -> tuple[bool, str]:
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() == 0:
            return False, "no CUDA GPU visible"
    except Exception as e:
        return False, str(e)
    if os.name == "nt":
        # a missing cuDNN DLL would crash the whole app, so check first
        missing = [n for n in ("cublas64_12.dll", "cudnn_ops64_9.dll") if not _dll_found(n)]
        if missing:
            return False, "missing " + ", ".join(missing)
    return True, ""


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zа-яё]+", text.lower())


def is_wake_word(token: str) -> bool:
    if token.startswith(("капр", "capr", "kapr")):
        return True
    return any(difflib.SequenceMatcher(None, token, w).ratio() >= 0.75 for w in WAKE_FORMS)


class Transcriber:
    def __init__(self, log: Callable[[str], None] = print):
        self._log = log
        self._model = None
        self._lock = threading.Lock()
        self.ready = threading.Event()
        self.device = "loading"
        threading.Thread(target=self._load, daemon=True, name="whisper-load").start()

    def _load(self) -> None:
        from faster_whisper import WhisperModel
        _add_cuda_dll_dirs()
        ok, why = _gpu_ready()
        if ok:
            try:
                src = _model_source(GPU_MODEL)
                where = "from models/" if src != GPU_MODEL else "(first time: ~1.6 GB download)"
                self._log(f"[STT] Loading Whisper {GPU_MODEL} on GPU {where}...")
                m = WhisperModel(_model_source(GPU_MODEL), device="cuda",
                                 compute_type="float16")
                list(m.transcribe(np.zeros(16000, np.float32), language=LANGUAGE)[0])
                self._model, self.device = m, f"GPU, {GPU_MODEL}"
            except Exception as e:
                why = f"{e.__class__.__name__}: {e}"
        if self._model is None:
            self._log(f"[STT] GPU not used ({why}) — falling back to CPU.")
            self._log("      For GPU: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*")
            self._log(f"[STT] Loading Whisper {CPU_MODEL} on CPU...")
            self._model = WhisperModel(_model_source(CPU_MODEL), device="cpu",
                                       compute_type="int8")
            self.device = f"CPU, {CPU_MODEL}"
        self.ready.set()
        self._log(f"[STT] Whisper ready ({self.device}).")

    def transcribe(self, audio: np.ndarray) -> str:
        if not self.ready.wait(timeout=600):
            return ""
        with self._lock:
            segments, _ = self._model.transcribe(
                audio, language=LANGUAGE, beam_size=5,
                condition_on_previous_text=False, without_timestamps=True,
            )
            text = " ".join(s.text.strip() for s in segments).strip()
        low = text.lower()
        if any(h in low for h in HALLUCINATIONS):
            return ""
        return text

    # ── wake word helpers ────────────────────────────────────────────

    def confirm_wake(self, audio: np.ndarray) -> tuple[bool, str]:
        """Was it really «Капри»? Returns (yes/no, what Whisper heard)."""
        text = self.transcribe(audio)
        return any(is_wake_word(w) for w in _words(text)[:3]), text

    @staticmethod
    def split_command(text: str) -> tuple[bool, str]:
        """«Капри, открой стим» → (True, «открой стим»)."""
        words = list(re.finditer(r"[A-Za-zА-Яа-яЁё]+", text))
        for m in words[:3]:
            if is_wake_word(m.group().lower()):
                rest = text[m.end():].lstrip(" ,.!?:;—-")
                return True, rest.strip()
        return False, text.strip()

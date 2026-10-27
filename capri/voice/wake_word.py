"""
wake_word.py
Always-on listening for Capri's name ("Капри") — built to be cheap on CPU.

Each stage only runs when the previous one lets it through:
  1. Microphone, 30 ms blocks.
  2. Energy gate — is anyone talking at all? (a bit of numpy, ~free)
  3. Vosk, small Russian model, restricted to ONE word — runs only
     while there is speech, otherwise sleeps.

After «Капри» it records the command until you stop talking and hands
the audio over (on_command). Vosk can mishear similar words, so the
first bit of audio is also handed over right away (on_trigger) to be
double-checked by Whisper; cancel_command() aborts a false alarm.

Every minute the log shows how much CPU this actually costs.

Install:  pip install vosk
The speech model (~45 MB) is downloaded automatically on first start
into the models/ folder.
"""

import json
import queue
import threading
import time
import urllib.request
import zipfile
from collections import deque
from pathlib import Path
from typing import Callable

import numpy as np

# ── tuneable ─────────────────────────────────────────────────────────
WAKE_WORDS        = ["капри"]   # what she reacts to
MIN_CONFIDENCE    = 0.60        # raise if she reacts to random words
GATE_DB_ABOVE     = 9.0         # how much louder than room noise = "speech"
MIN_SPEECH_DBFS   = -55.0       # never treat anything quieter as speech
PREROLL_MS        = 300         # audio kept from before speech started
HANGOVER_MS       = 700         # keep listening this long after speech stops
COOLDOWN_S        = 1.5         # ignore repeats right after a detection
STATS_EVERY_S     = 60          # CPU report interval in the log
COMMAND_END_MS    = 900         # silence that ends a voice command
COMMAND_WAIT_MS   = 5000        # give up if nothing is said after «Капри»
COMMAND_MAX_MS    = 15000       # hard limit for one command
# ─────────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16_000
BLOCK_MS    = 30
BLOCK       = SAMPLE_RATE * BLOCK_MS // 1000

MODEL_NAME = "vosk-model-small-ru-0.22"
MODEL_URL  = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


def is_available() -> bool:
    try:
        import vosk          # noqa: F401
        import sounddevice   # noqa: F401
        return True
    except ImportError:
        return False


class WakeWordListener:
    """
    Callbacks (called from the audio thread — keep them quick):
      on_trigger(audio)  Vosk thinks it heard «Капри»; audio = that bit
      on_command(audio)  the whole thing: «Капри» + command (float32, 16 kHz)
    """

    def __init__(self, on_trigger: Callable, on_command: Callable,
                 log: Callable[[str], None] = print):
        self._on_trigger = on_trigger
        self._on_command = on_command
        self._log = log
        self._enabled = threading.Event()
        self._stop = threading.Event()
        self._cancel = threading.Event()
        self._q: "queue.Queue[bytes]" = queue.Queue(maxsize=300)
        self._cooldown_until = 0.0
        self._cancel_reason = "false alarm"

    # ── public ───────────────────────────────────────────────────────

    def start(self, enabled: bool = True) -> None:
        if enabled:
            self._enabled.set()
        threading.Thread(target=self._run, daemon=True, name="wake-word").start()

    def set_enabled(self, on: bool) -> None:
        if on:
            self._enabled.set()
        else:
            self._enabled.clear()     # mic is released, nothing runs
        self._log(f"[Wake] {'on' if on else 'off'}")

    def is_enabled(self) -> bool:
        return self._enabled.is_set()

    def cancel_command(self, reason: str = "false alarm") -> None:
        """Stop recording the command and go back to listening."""
        self._cancel_reason = reason
        self._cancel.set()

    def stop(self) -> None:
        self._stop.set()
        self._enabled.clear()

    # ── model ────────────────────────────────────────────────────────

    def _ensure_model(self) -> Path:
        path = MODELS_DIR / MODEL_NAME
        if (path / "conf").is_dir():
            return path
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = MODELS_DIR / (MODEL_NAME + ".zip.part")
        self._log("[Wake] Downloading Russian speech model (~45 MB, once)...")
        with urllib.request.urlopen(MODEL_URL, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length", 0))
            done, step = 0, max(total // 5, 1)
            while chunk := r.read(1 << 16):
                f.write(chunk)
                done += len(chunk)
                if total and done // step != (done - len(chunk)) // step:
                    self._log(f"[Wake]   {done * 100 // total}%")
        with zipfile.ZipFile(tmp) as z:
            z.extractall(MODELS_DIR)
        tmp.unlink()
        self._log("[Wake] Model ready.")
        return path

    # ── worker ───────────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model, SetLogLevel
            SetLogLevel(-1)
            model = Model(str(self._ensure_model()))
            grammar = json.dumps(WAKE_WORDS + ["[unk]"], ensure_ascii=False)
            rec = KaldiRecognizer(model, SAMPLE_RATE, grammar)
            rec.SetWords(True)
        except Exception as e:
            self._log(f"[Wake] Disabled: {e}")
            return

        def callback(indata, frames, t, status):
            try:
                self._q.put_nowait(bytes(indata))
            except queue.Full:
                pass

        while not self._stop.is_set():
            if not self._enabled.wait(timeout=0.5):
                continue
            try:
                with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK,
                                       channels=1, dtype="int16", callback=callback):
                    self._log("[Wake] Listening — say «Капри».")
                    self._listen(rec)
            except Exception as e:
                self._log(f"[Wake] Microphone error: {e}")
                time.sleep(5)
            rec.Reset()
            while not self._q.empty():
                self._q.get_nowait()

    @staticmethod
    def _db(data: bytes) -> float:
        x = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        return float(20 * np.log10(np.sqrt(np.mean(x * x)) / 32768 + 1e-9))

    @staticmethod
    def _to_float(chunks) -> np.ndarray:
        raw = b"".join(chunks)
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    def _listen(self, rec) -> None:
        bpms = BLOCK_MS
        preroll = deque(maxlen=PREROLL_MS // bpms)
        noise_db = None
        calib = []

        # wake-word stage
        active = False
        hang = 0
        utter: list[bytes] = []     # current utterance, from pre-roll on
        utter_start = 0             # Vosk clock (samples) at utterance start
        vosk_clock = 0              # samples fed to Vosk since it was created

        # command stage
        cmd: list[bytes] | None = None
        cmd_speech = False
        cmd_silence = 0

        cpu0, t0 = time.thread_time(), time.monotonic()
        blocks = fed = 0

        def feed(d: bytes):
            nonlocal vosk_clock, fed
            vosk_clock += len(d) // 2
            fed += 1
            return rec.AcceptWaveform(d)

        while self._enabled.is_set() and not self._stop.is_set():
            try:
                data = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            blocks += 1
            db = self._db(data)

            # learn the room's background noise (first second, then slowly)
            if noise_db is None:
                calib.append(db)
                if len(calib) >= 1000 // bpms:
                    noise_db = float(np.median(calib))
                continue
            if db < noise_db:
                noise_db = 0.9 * noise_db + 0.1 * db
            else:
                noise_db = 0.999 * noise_db + 0.001 * db
            gate = max(noise_db + GATE_DB_ABOVE, MIN_SPEECH_DBFS)
            speech = db > gate

            # ── command stage: record until the user stops talking ───
            if cmd is not None:
                cmd.append(data)
                if speech:
                    cmd_speech, cmd_silence = True, 0
                else:
                    cmd_silence += 1
                length = len(cmd) * bpms
                done = (
                    (cmd_speech and cmd_silence * bpms >= COMMAND_END_MS)
                    or (not cmd_speech and length >= COMMAND_WAIT_MS)
                    or length >= COMMAND_MAX_MS
                )
                if self._cancel.is_set():
                    self._log(f"[Wake] Cancelled ({self._cancel_reason}) — back to listening.")
                    cmd = None
                elif done:
                    # trim trailing silence, keep a little
                    keep = max(0, cmd_silence - 300 // bpms)
                    audio = self._to_float(utter + cmd[: len(cmd) - keep])
                    cmd = None
                    self._on_command(audio)
                if cmd is None:
                    self._cancel.clear()
                    rec.Reset()
                    active, hang, utter = False, 0, []
                    preroll.clear()
                continue

            # ── wake stage: gate → Vosk ──────────────────────────────
            if speech:
                hang = HANGOVER_MS // bpms
                if not active:
                    active = True
                    utter = list(preroll)
                    utter_start = vosk_clock
                    for d in preroll:
                        feed(d)
                    preroll.clear()

            if not active:
                preroll.append(data)
            else:
                utter.append(data)
                result = None
                if feed(data):
                    result = json.loads(rec.Result())
                if not speech:
                    hang -= 1
                    if hang <= 0:
                        active = False
                        result = result or json.loads(rec.FinalResult())
                        rec.Reset()
                end = self._find_wake(result) if result else None
                if end is not None:
                    # split the utterance at the end of «Капри»
                    cut = max(0, min(int(end * SAMPLE_RATE) - utter_start,
                                     len(utter) * BLOCK))
                    blk = cut // BLOCK + 1
                    head, tail = utter[:blk], utter[blk:]
                    margin = utter[blk: blk + 250 // bpms]
                    self._on_trigger(self._to_float(head + margin))
                    # start recording the command (tail = already said)
                    utter, cmd = head, list(tail)
                    flags = [self._db(d) > gate for d in tail]
                    cmd_speech = any(flags)
                    cmd_silence = 0
                    for f in reversed(flags):
                        if f:
                            break
                        cmd_silence += 1
                    self._cancel.clear()
                    rec.Reset()
                    active, hang = False, 0
                elif not active:
                    utter = []

            # CPU report
            now = time.monotonic()
            if now - t0 >= STATS_EVERY_S:
                cpu = (time.thread_time() - cpu0) / (now - t0) * 100
                self._log(f"[Wake] CPU {cpu:.1f}% of one core, "
                          f"speech {fed * 100 / max(blocks, 1):.0f}% of the time, "
                          f"noise {noise_db:.0f} dB")
                cpu0, t0, blocks, fed = time.thread_time(), now, 0, 0

    def _find_wake(self, result: dict):
        """Returns the end time (s, Vosk clock) of «Капри», or None."""
        for w in result.get("result", []):
            if w.get("word") not in WAKE_WORDS:
                continue
            if w.get("conf", 0.0) < MIN_CONFIDENCE:
                continue
            if time.monotonic() < self._cooldown_until:
                return None
            self._cooldown_until = time.monotonic() + COOLDOWN_S
            self._log(f"[Wake] Vosk: «{w['word']}»?")
            return float(w.get("end", 0.0))
        return None

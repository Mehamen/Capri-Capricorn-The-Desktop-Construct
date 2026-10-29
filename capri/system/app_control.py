"""
app_control.py
Capri controls apps through their interface — like you would by hand.

Music (Spotify, YouTube in the browser, any player) — Windows media keys:
    «следующий трек», «предыдущий трек», «пауза», «продолжи»,
    «громче», «тише», «громкость 30», «выключи звук», «что играет»
Spotify search:
    «найди в спотифай <что-то>»
Discord — quick switcher (Ctrl+K) and default hotkeys:
    «зайди в войс игрульки твари», «выключи микрофон», «выключи звук в дискорде»

Everything Discord-related runs in the background, and Capri puts you back
into the window you were in.
"""

import os
import re
import threading
import time
import urllib.parse
from typing import Callable, Optional

from capri.system import win_input as w

SPOTIFY_EXE = "spotify.exe"
DISCORD_EXE = "discord.exe"

SONG = r"(?:трек\w*|песн\w*|композици\w*|музык\w*)"


class AppControls:
    def __init__(self, launch_app: Callable[[str], bool], log=print):
        """launch_app('дискорд') → opens the program (uses apps.json etc.)"""
        self._launch_app = launch_app
        self._log = log
        self._busy = threading.Lock()

    # ── entry point ──────────────────────────────────────────────────

    def try_handle(self, t: str) -> Optional[str]:
        """t = normalized lowercase text. Returns Capri's reply or None."""
        t = t.replace(",", " ")
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"^(?:пожалуйста|плиз|капри) ", "", t)
        for handler in (self._discord, self._music):
            reply = handler(t)
            if reply is not None:
                return reply
        return None

    # ── music ────────────────────────────────────────────────────────

    def _spotify_title(self) -> Optional[str]:
        """'Artist - Song' while playing, 'Spotify…' when paused, None if not running."""
        titles = [w.title_of(h) for h in w.windows_of(SPOTIFY_EXE)]
        titles = [x for x in titles if x and x not in ("Default IME", "MSCTFIME UI", "GDI+ Window")]
        if not titles:
            return None
        playing = [x for x in titles if " - " in x]
        return playing[0] if playing else titles[0]

    def _is_playing(self) -> Optional[bool]:
        title = self._spotify_title()
        if title is None:
            return None
        return " - " in title

    def _music(self, t: str) -> Optional[str]:
        m = re.search(r"^(?:найди|поищи|включи|поставь)\s+(?:в спотиф\w*|на спотиф\w*)\s+(.+)$", t) \
            or re.search(r"^(?:найди|поищи)\s+(.+?)\s+(?:в|на) спотиф\w*$", t)
        if m:
            q = m.group(1)
            if w.IS_WINDOWS:
                os.startfile("spotify:search:" + urllib.parse.quote(q))
            return f"открыла поиск «{q}» в спотифае 🔎 выбери, что включить"
        # the rest only for short phrases — so normal chat isn't hijacked
        if len(t.split()) > 6:
            return None
        if re.search(rf"(следующ\w*|некст)( {SONG})?$|переключи {SONG}|скипни|скип$|пропусти {SONG}|^дальше$", t):
            w.press(w.VK_MEDIA_NEXT)
            return "следующий трек ⏭"
        if re.search(rf"предыдущ\w*( {SONG})?$|прошл\w* {SONG}|верни {SONG}|{SONG} назад$", t):
            w.press(w.VK_MEDIA_PREV)
            return "предыдущий трек ⏮"
        if re.search(rf"^(?:поставь )?(?:на )?пауз\w*|останови {SONG}|стоп {SONG}|выключи {SONG}|^стоп$", t):
            if self._is_playing() is False:
                return "уже на паузе ⏸"
            w.press(w.VK_MEDIA_PLAY_PAUSE)
            return "пауза ⏸"
        if re.search(rf"^продолж\w*|сними с паузы|сними паузу|^(?:включи|вруби|запусти) {SONG}$|^играй$", t):
            if self._is_playing() is True:
                return "уже играет ▶"
            w.press(w.VK_MEDIA_PLAY_PAUSE)
            return "играет ▶"
        m = re.search(r"громкост\w* (?:на )?(\d{1,3})", t)
        if m:
            level = max(0, min(100, int(m.group(1))))
            w.tap(w.VK_VOLUME_DOWN, 50)            # to 0 (each step = 2%)
            w.tap(w.VK_VOLUME_UP, level // 2)
            return f"громкость {level // 2 * 2}% 🔊"
        if re.search(r"(?:сделай |сделать |чуть |ещ[её] |по)?громче|прибав\w* (?:звук|громкость)|увелич\w* громкость", t):
            w.tap(w.VK_VOLUME_UP, 5)
            return "громче 🔊"
        if re.search(r"(?:сделай |сделать |чуть |ещ[её] |по)?тише|убав\w* (?:звук|громкость)|уменьш\w* громкость", t):
            w.tap(w.VK_VOLUME_DOWN, 5)
            return "тише 🔉"
        if re.search(r"^(?:выключи|убери|отключи) звук$|^без звука$", t):
            w.press(w.VK_VOLUME_MUTE)
            return "звук выключен/включён 🔇"
        if re.search(rf"что (?:сейчас )?(?:играет|за {SONG})|какой (?:это |сейчас )?{SONG}|как называется {SONG}", t):
            title = self._spotify_title()
            if title is None:
                return "спотифай не запущен"
            if " - " not in title:
                return "в спотифае пауза ⏸"
            return f"сейчас играет: {title} 🎵"
        return None

    # ── discord ──────────────────────────────────────────────────────

    def _discord_window(self):
        for h in w.windows_of(DISCORD_EXE):
            if w.title_of(h).endswith("Discord"):
                return h
        wins = w.windows_of(DISCORD_EXE)
        return wins[0] if wins else None

    def _discord(self, t: str) -> Optional[str]:
        in_dc = r"(?: в (?:дискорд\w*|дс|дискорт\w*))?"
        m = re.search(
            r"(?:зайди|зайти|зайдем|зайдём|подключись|подключи меня|войди|перейди|закинь меня|кинь меня)"
            r"\s+(?:в|к|на)\s+"
            r"(?:войс канал\w*|войс\w*|войз\w*|voice|голосовух\w*|голосов\w*(?: канал\w*)?|канал\w*)"
            rf"\s+(.+?){in_dc}$", t)
        if m:
            channel = m.group(1).strip()
            self._in_background(self._join_voice, channel)
            return f"захожу в войс «{channel}» 🎧"
        if re.search(rf"(?:выключи|включи|вруби|отключи|замуть|размуть)\s+(?:мне\s+)?(?:микрофон|мик|микро|микрофончик){in_dc}$|^(?:замуть|размуть) меня", t):
            self._in_background(self._discord_hotkey, (w.VK_CONTROL, w.VK_SHIFT, w.vk_letter("M")))
            return "переключаю микрофон в дискорде 🎙"
        if re.search(r"(?:выключи|включи|отключи)\s+(?:звук|наушники)\s+в\s+(?:дискорд\w*|дс)$|^заглуши дискорд", t):
            self._in_background(self._discord_hotkey, (w.VK_CONTROL, w.VK_SHIFT, w.vk_letter("D")))
            return "переключаю звук в дискорде 🎧"
        return None

    def _in_background(self, fn, arg) -> None:
        def run():
            if not self._busy.acquire(timeout=10):
                return
            try:
                fn(arg)
            except Exception as e:
                self._log(f"[AppControl] {fn.__name__} failed: {e}")
            finally:
                self._busy.release()
        threading.Thread(target=run, daemon=True).start()

    def _ensure_discord(self):
        hwnd = self._discord_window()
        if hwnd:
            return hwnd
        self._log("[AppControl] Discord not running — starting it")
        self._launch_app("дискорд")
        for _ in range(40):                   # up to ~20 s
            time.sleep(0.5)
            hwnd = self._discord_window()
            if hwnd:
                time.sleep(4)                 # let it finish loading
                return hwnd
        return None

    def _join_voice(self, channel: str) -> None:
        prev = w.foreground()
        hwnd = self._ensure_discord()
        if not hwnd or not w.focus(hwnd):
            self._log("[AppControl] could not bring Discord to the front")
            return
        time.sleep(0.3)
        w.press(w.VK_ESCAPE)                  # close a popup if one is open
        time.sleep(0.15)
        w.press(w.VK_CONTROL, w.vk_letter("K"))   # quick switcher
        time.sleep(0.5)
        w.type_text("!" + channel)            # "!" = only voice channels
        time.sleep(0.9)
        w.press(w.VK_RETURN)
        self._log(f"[AppControl] Discord: joining voice «{channel}»")
        time.sleep(0.8)
        if prev and prev != hwnd:
            w.focus(prev)

    def _discord_hotkey(self, keys) -> None:
        prev = w.foreground()
        hwnd = self._discord_window()
        if not hwnd or not w.focus(hwnd):
            self._log("[AppControl] Discord is not running")
            return
        time.sleep(0.3)
        w.press(*keys)
        time.sleep(0.3)
        if prev and prev != hwnd:
            w.focus(prev)

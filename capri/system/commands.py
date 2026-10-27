"""
commands.py
Simple PC commands Capri handles herself, without the AI model:

    «открой стим», «запусти дискорд», «открой браузер», «открой ютуб»,
    «найди в гугле котиков» …

Typed in the chat or said by voice («Капри, открой стим»).
Anything that isn't a command goes to the AI as usual.

Where she looks for programs:
  1. apps.json in the project root — your own names → path / site / command
  2. built-in list below (popular programs and sites)
  3. shortcuts in the Start menu and on the desktop (found automatically)
"""

import difflib
import json
import os
import re
import urllib.parse
import webbrowser
from pathlib import Path

APPS_FILE = Path(__file__).resolve().parents[2] / "apps.json"

OPEN_VERBS   = r"(?:открой|открыть|запусти|запустить|включи|включить|зайди на|зайди в|перейди на)"
SEARCH_VERBS = r"(?:найди|найти|поищи|загугли|погугли)"
FILLER = {"пожалуйста", "мне", "плиз", "программу", "приложение", "сайт", "игру", "мой", "мою"}

# name you say → what to launch (path, URL, protocol or command)
BUILTIN = {
    # programs
    "стим": "steam://open/main",             "steam": "steam://open/main",
    "блокнот": "notepad.exe",                "калькулятор": "calc.exe",
    "проводник": "explorer.exe",             "диспетчер задач": "taskmgr.exe",
    "панель управления": "control.exe",      "настройки": "ms-settings:",
    "paint": "mspaint.exe",                  "пейнт": "mspaint.exe",
    "командную строку": "cmd.exe",           "терминал": "wt.exe",
    # "find:" = look for a Start-menu / desktop shortcut with that name
    "вс код": "find:visual studio code",     "vs code": "find:visual studio code",
    "визуал студио": "find:visual studio code",
    "дискорд": "find:discord",               "телеграм": "find:telegram",
    "телегу": "find:telegram",               "хром": "find:google chrome",
    "спотифай": "find:spotify",              "эпик": "find:epic games launcher",
    "эпик геймс": "find:epic games launcher", "обс": "find:obs studio",
    "ворд": "find:word",                     "эксель": "find:excel",
    "фигму": "find:figma",                   "докер": "find:docker desktop",
    "ватсап": "find:whatsapp",               "зум": "find:zoom",
    "роблокс": "find:roblox player",         "мейдал": "find:medal",
    "майнкрафт": "find:minecraft",           "майн": "find:minecraft",
    "юнити": "find:unity hub",               "блендер": "find:blender",
    "эдж": "find:microsoft edge",            "яндекс браузер": "find:yandex",
    # browser & sites
    "браузер": "https://www.google.com",     "гугл": "https://www.google.com",
    "ютуб": "https://www.youtube.com",       "youtube": "https://www.youtube.com",
    "вк": "https://vk.com",                  "вконтакте": "https://vk.com",
    "твич": "https://www.twitch.tv",         "гитхаб": "https://github.com",
    "github": "https://github.com",          "почту": "https://mail.google.com",
    "почта": "https://mail.google.com",      "гугл диск": "https://drive.google.com",
    "переводчик": "https://translate.google.com",
    "карты": "https://yandex.ru/maps",       "погоду": "https://yandex.ru/pogoda",
}

_TRANSLIT = dict(zip(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    ["a","b","v","g","d","e","e","zh","z","i","y","k","l","m","n","o","p","r","s",
     "t","u","f","h","ts","ch","sh","sch","","y","","e","yu","ya"],
))

SKIP_SHORTCUT = ("uninstall", "удал", "readme", "help", "documentation", "website",
                 "release notes", "license", "справка")


def translit(text: str) -> str:
    return "".join(_TRANSLIT.get(c, c) for c in text.lower())


def _norm(text: str, keep_commas: bool = False) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s,]" if keep_commas else r"[^\w\s]", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    return re.sub(r"\s+", " ", text).strip()


def _split_exe(option: str):
    """'C:\\...\\Update.exe --processStart Discord.exe' -> (exe path, [args])"""
    m = re.match(r'^"?(.+?\.exe)"?(?:\s+(.*))?$', option.strip(), re.IGNORECASE)
    if not m:
        return option.strip(), []
    return m.group(1), (m.group(2) or "").split()


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


class CommandRunner:
    def __init__(self, log=print):
        self._log = log
        self._user = self._load_user_apps()
        self._shortcuts = self._scan_shortcuts()
        self._log(f"[Commands] {len(self._shortcuts)} shortcuts found, "
                  f"{len(self._user)} own names in apps.json")

    # ── setup ────────────────────────────────────────────────────────

    def _load_user_apps(self) -> dict:
        if not APPS_FILE.exists():
            example = {
                "_как пользоваться": "добавь строку: \"как ты называешь\": \"путь, сайт или команда\". find:имя = найти ярлык в Пуске, || = запасной вариант",
                "_пример": {"моя игра": "C:\\Games\\MyGame\\game.exe",
                            "кинопоиск": "https://www.kinopoisk.ru"},
            }
            try:
                APPS_FILE.write_text(json.dumps(example, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
            except OSError:
                pass
            return {}
        try:
            data = json.loads(APPS_FILE.read_text(encoding="utf-8"))
            return {_norm(k): v for k, v in data.items()
                    if not k.startswith("_") and isinstance(v, str)}
        except Exception as e:
            self._log(f"[Commands] apps.json has an error: {e}")
            return {}

    def _scan_shortcuts(self) -> dict:
        if os.name != "nt":
            return {}
        env = os.environ
        roots = [
            Path(env.get("ProgramData", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path(env.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
            Path.home() / "Desktop",
            Path.home() / "OneDrive" / "Desktop",
            Path(env.get("PUBLIC", "")) / "Desktop",
        ]
        found = {}
        for root in roots:
            if not root.is_dir():
                continue
            for p in root.rglob("*"):
                if p.suffix.lower() not in (".lnk", ".url"):
                    continue
                name = _norm(p.stem)
                if not name or any(s in name for s in SKIP_SHORTCUT):
                    continue
                found.setdefault(name, str(p))
        return found

    # ── matching ─────────────────────────────────────────────────────

    def _find_shortcut(self, name: str):
        name = _norm(name)
        if name in self._shortcuts:
            return name, self._shortcuts[name]
        best, score = None, 0.0
        for n, path in self._shortcuts.items():
            s = 1.0 if n.startswith(name) else _similar(name, n)
            if s > score:
                best, score = (n, path), s
        return best if score >= 0.8 else None

    def _lookup(self, target: str):
        hit = self._lookup_raw(target)
        if not hit:
            return None
        name, value = hit
        # "find:claude || https://claude.ai" → first option that works
        for option in (o.strip() for o in value.split("||")):
            if option.startswith("find:"):
                found = self._find_shortcut(option[5:])
                if found:
                    return Path(found[1]).stem, found[1]
            elif re.match(r"^[a-z][a-z0-9+.-]+:", option, re.IGNORECASE) \
                    or os.path.exists(_split_exe(option)[0]) \
                    or not re.search(r"[\\/]", option):
                # URL / protocol / existing file / plain command like notepad.exe
                return name, option
        return None

    def _lookup_raw(self, target: str):
        """Returns (display name, what to launch) or None."""
        t = _norm(target)
        words = [w for w in t.split() if w not in FILLER]
        t = " ".join(words)
        if not t:
            return None
        t_lat = translit(t)

        # 1–2: own names and built-ins (exact, then close match)
        for table in (self._user, BUILTIN):
            if t in table:
                return t, table[t]
        best, score = None, 0.0
        for table in (self._user, BUILTIN):
            for name, target_ in table.items():
                s = max(_similar(t, name), _similar(t_lat, translit(name)))
                if s > score:
                    best, score = (name, target_), s
        if best and score >= 0.82:
            return best

        # 3: Start menu / desktop shortcuts (names are mostly English)
        best, score = None, 0.0
        for name, path in self._shortcuts.items():
            cands = [name] + name.split()
            s = max(max(_similar(t, c), _similar(t_lat, c)) for c in cands)
            # whole-name match is worth a bit more than one word of it
            s += 0.05 * max(_similar(t, name), _similar(t_lat, name))
            if s > score:
                best, score = (Path(path).stem, path), s
        if best and score >= 0.78:
            return best
        return None

    # ── public ───────────────────────────────────────────────────────

    def try_handle(self, text: str):
        """If text is a command — do it and return Capri's reply. Else None."""
        t = _norm(text, keep_commas=True).strip(" ,")

        m = re.match(rf"^(?:пожалуйста )?{SEARCH_VERBS}(?: в (?:гугле|google|интернете|браузере))? (.+)$", t)
        if m:
            query = m.group(1)
            webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(query))
            return f"ищу «{query}» в гугле"

        m = re.match(rf"^(?:пожалуйста )?{OPEN_VERBS} (.+)$", t)
        if not m:
            return None
        # «открой стим и дискорд» → both
        targets = [x for x in re.split(r" и | а потом | потом |, ", m.group(1)) if x.strip()]
        opened, missing, failed = [], [], []
        for target in targets[:4]:
            hit = self._lookup(target)
            if hit is None:
                self._log(f"[Commands] not found: {target!r}")
                missing.append(target)
                continue
            name, what = hit
            try:
                self._launch(what)
                self._log(f"[Commands] open {name!r} → {what}")
                opened.append(name)
            except Exception as e:
                self._log(f"[Commands] failed to open {what!r}: {e}")
                failed.append(name)
        parts = []
        if opened:
            parts.append("открываю " + ", ".join(opened) + " ✓")
        if failed:
            parts.append("не получилось открыть " + ", ".join(failed))
        if missing:
            parts.append("не нашла " + ", ".join(f"«{t}»" for t in missing)
                         + " 😕 можно добавить в apps.json")
        return "; ".join(parts)

    @staticmethod
    def _launch(what: str) -> None:
        exe, args = _split_exe(what)
        if re.match(r"^https?://", what):
            webbrowser.open(what)
        elif args:                     # program with parameters
            import subprocess
            subprocess.Popen([exe] + args, cwd=os.path.dirname(exe) or None)
        elif os.name == "nt":
            os.startfile(what)     # .exe, .lnk, steam://, ms-settings: …
        else:
            webbrowser.open(what)

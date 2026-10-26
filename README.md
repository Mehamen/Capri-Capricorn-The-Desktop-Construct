# Capri — русская версия (форк)

> **Это форк, а не мой проект.**
> Оригинальный автор Capri — **[Juliowiwiwiwi](https://github.com/Juliowiwiwiwi)**.
> Оригинальный репозиторий: **[Juliowiwiwiwi/Capri-Capricorn-The-Desktop-Construct](https://github.com/Juliowiwiwiwi/Capri-Capricorn-The-Desktop-Construct)**
>
> Персонаж, арт, идея, интерфейс и основной код принадлежат автору оригинала.
> В этом форке я только исправляю ошибки и добавляю свои функции — список ниже.

*Маленький киберпанк-компаньон для рабочего стола Windows.*

Capri — анимированный персонаж, который живёт на рабочем столе, с чатом
в стиле терминала. Отвечает локальная нейросеть через
[Ollama](https://ollama.com/) — без облака и без API-ключей.

![Capri на рабочем столе](assets/ui/capri1.png)
![Чат Capri](assets/ui/caprichat.png)

---

## Что изменено в этом форке

| Изменение | Файлы |
|---|---|
| **Исправлен Modelfile** — в оригинале 4 строки текста стояли перед `FROM`, из-за чего `ollama create` падал с ошибкой. Перенесены внутрь `SYSTEM`. | `Modelfile` |
| **Ответы на русском** — добавлено правило «всегда отвечай по-русски». | `Modelfile` |
| **Заполнен `requirements.txt`** — в оригинале он пустой. | `requirements.txt` |
| **Нет ошибки `timed out`** — таймаут ответа увеличен с 60 с до 5 мин (первая загрузка модели на слабом ПК идёт дольше минуты), модель держится в памяти 30 мин между сообщениями. | `capri/ai/model_client.py` |
| **Автозапуск с Windows** — галочка «↻ Start with Windows» в меню по правому клику на Capri. | `capri/system/autostart.py`, `capri/desktop/window.py` |
| **Запуск без консоли** — `run_capri.pyw`, логи пишутся в `capri.log`. | `run_capri.pyw` |
| **Ollama запускается сама**, если ещё не запущена при старте Capri. | `capri/system/ollama_service.py` |
| **Только одна Capri** — повторный запуск не создаёт вторую копию, а показывает уже открытую. | `capri/system/single_instance.py`, `capri/main.py` |

### В планах

- [ ] Голосовой ввод по слову «Капри» (как «Окей, Google»)
- [ ] Русская озвучка ответов (Piper)
- [ ] Команды для открытия приложений («открой стим»)

---

## Установка

**Нужно:** Windows 10/11, Python 3.11+, [Ollama](https://ollama.com/download).
Видеокарта не обязательна, но без неё ответы идут медленнее.

```powershell
git clone https://github.com/Mehamen/Capri-Capricorn-The-Desktop-Construct
cd Capri-Capricorn-The-Desktop-Construct

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

> Если PowerShell не даёт активировать окружение:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`

### Модель

После установки Ollama **перезапусти терминал** (иначе команда `ollama` не найдётся), затем:

```powershell
ollama pull gemma3:4b
ollama create capri -f .\Modelfile
ollama list        # должна появиться capri:latest
```

После любых правок в `Modelfile` модель нужно пересобрать той же командой `ollama create`.

### Запуск

```powershell
python -m capri.main
```

или двойной клик по `run_capri.pyw` (без окна консоли).

- **Левый клик** по Capri — открыть / закрыть чат
- **Правый клик** — меню: сон, автозапуск, выход

### Автозапуск

Правый клик по Capri → **↻ Start with Windows**.
Включать нужно из запуска через `.venv` — в автозагрузку записывается тот Python, из которого запущена Capri.
В диспетчере задач на вкладке «Автозагрузка» запись видна как **Python**.

---

## Частые проблемы

| Проблема | Решение |
|---|---|
| `ollama : The term 'ollama' is not recognized` | Ollama не установлена, или терминал/VS Code не перезапущены после установки. |
| `// ERROR: timed out` | Модель грузится слишком долго. В этом форке исправлено; прогрей модель заранее: `ollama run capri "привет"`. |
| `// CONNECTION LOST — is Ollama running?` | Запусти Ollama из меню «Пуск». Проверь `ollama list` — есть ли `capri:latest`. |
| Отвечает по-английски | Пересобери модель: `ollama create capri -f .\Modelfile`. |
| `No module named 'PySide6'` | Запущено не из `.venv`. Активируй окружение и поставь зависимости. |
| `[Voice] Running text-only` | Это нормально — голос ещё не настроен, работает текстовый чат. |

---

## Стек

Python · PySide6 · Ollama · Gemma 3 4B · (в планах: faster-whisper, Piper)

## Авторы

- **[Juliowiwiwiwi](https://github.com/Juliowiwiwiwi)** — автор оригинального проекта Capri: персонаж, арт, интерфейс, основной код.
- **Mehamen** — форк: исправления, русский язык, автозапуск и прочее из списка выше.

## Лицензия

У оригинального проекта лицензия не указана, поэтому все права на оригинальный код и арт остаются за его автором.
Этот форк сделан в некоммерческих целях. Если автор оригинала против — форк будет удалён.

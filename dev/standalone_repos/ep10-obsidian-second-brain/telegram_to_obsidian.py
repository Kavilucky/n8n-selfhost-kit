#!/usr/bin/env python3
"""Голосовое из Telegram -> текст (локальный Whisper) -> заметка Markdown в хранилище Obsidian.

Режимы:
  python telegram_to_obsidian.py --file запись.ogg      обработать один аудиофайл (Telegram не нужен)
  python telegram_to_obsidian.py --process-inbox        обработать все файлы из raw_inbox/
  python telegram_to_obsidian.py --poll                 слушать личного бота (токен в .env), скачивать голосовые и обрабатывать

Теги и сроки выделяются правилами по ключевым словам, датам и регулярным выражениям (без видеокарты, без внешних сервисов).
Расшифровка идёт локально через faster-whisper. Исходные аудио не удаляются: после обработки они переезжают в raw_inbox/done/.
Единственное, что идёт через серверы Telegram, это само сообщение до вашего бота.
"""
import argparse
import datetime as dt
import json
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIO_EXT = {".ogg", ".oga", ".opus", ".mp3", ".wav", ".m4a", ".flac"}

# ---------- настройки ----------


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    base = Path(path).resolve().parent
    vault = Path(cfg["vault_dir"])
    cfg["vault"] = vault if vault.is_absolute() else (base / vault).resolve()
    return cfg


def load_env(path):
    env = {}
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ---------- расшифровка (локальный Whisper) ----------
_model = None


def transcribe(path, cfg):
    global _model
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("Не установлен faster-whisper: pip install faster-whisper")
    if _model is None:
        _model = WhisperModel(cfg.get("whisper_model", "small"), device="cpu", compute_type="int8")
    segs, _ = _model.transcribe(str(path), language=cfg.get("language", "ru"), vad_filter=True)
    return " ".join(s.text.strip() for s in segs).strip()


# ---------- выделение сути и тегов: правила ----------
MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "мая": 5, "июн": 6, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
WEEKDAYS = {"понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3, "пятниц": 4, "суббот": 5, "воскресень": 6}


def extract_due(text, now):
    """Срок из фразы: сегодня, завтра, послезавтра, день недели, 05.10 или «5 октября». Вернёт YYYY-MM-DD или ''."""
    low = text.lower()
    today = now.date()
    if "послезавтра" in low:
        return str(today + dt.timedelta(days=2))
    if "завтра" in low:
        return str(today + dt.timedelta(days=1))
    if "сегодня" in low:
        return str(today)
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", low)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        y += 2000 if y < 100 else 0
        try:
            res = dt.date(y, mo, d)
            if not m.group(3) and res < today:
                res = dt.date(y + 1, mo, d)
            return str(res)
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})\s+([а-я]+)", low)
    if m:
        for stem, mo in MONTHS.items():
            if m.group(2).startswith(stem):
                try:
                    res = dt.date(today.year, mo, int(m.group(1)))
                    if res < today:
                        res = dt.date(today.year + 1, mo, int(m.group(1)))
                    return str(res)
                except ValueError:
                    break
    for stem, wd in WEEKDAYS.items():
        if re.search(r"\b" + stem, low):
            delta = (wd - today.weekday()) % 7 or 7
            return str(today + dt.timedelta(days=delta))
    return ""


def extract_tags(text, rules):
    low = text.lower()
    tags = []
    for tag, stems in rules.items():
        if any(re.search(r"\b" + re.escape(s.lower()), low) for s in stems):
            tags.append(tag)
    return tags or ["входящее"]


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def make_title(text):
    first = sentences(text)[0] if text else "Голосовая заметка"
    first = re.sub(r"\s+", " ", first).strip(" .!?")
    return (first[:60].rsplit(" ", 1)[0] if len(first) > 60 else first) or "Голосовая заметка"


def make_summary(text):
    s = sentences(text)
    return " ".join(s[:2])[:280] if s else ""


# ---------- опциональный модуль Ollama (выключен; включить, убрав комментарии, нужен запущенный Ollama) ----------
# import urllib.request, json
# def ollama_tags(text, model="qwen2.5:3b"):
#     body = json.dumps({"model": model, "stream": False, "format": "json",
#                        "prompt": "Верни JSON {\"tags\": [до 4 коротких тегов на русском]} для заметки:\n" + text}).encode()
#     req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=body, headers={"Content-Type": "application/json"})
#     with urllib.request.urlopen(req, timeout=120) as r:
#         return json.loads(json.loads(r.read())["response"]).get("tags", [])


# ---------- запись заметки ----------


def slugify(s):
    s = re.sub(r"[^0-9A-Za-zА-Яа-яЁё]+", "-", s.lower()).strip("-")
    return s[:40] or "zametka"


def find_links(notes_dir, tags, limit=5):
    """Ссылки [[...]] на существующие заметки с общими тегами: именно они рисуют связи в графе Obsidian."""
    out = []
    for p in sorted(Path(notes_dir).glob("*.md"), reverse=True):
        head = p.read_text(encoding="utf-8").split("---")
        if len(head) < 3:
            continue
        m = re.search(r"^tags:\s*\[(.*?)\]", head[1], re.M)
        if m and set(t.strip() for t in m.group(1).split(",")) & set(tags):
            out.append(f"- [[{p.stem}]]")
        if len(out) >= limit:
            break
    return "\n".join(out) or "- (пока нет)"


def write_note(text, cfg, now):
    vault = cfg["vault"]
    notes = vault / "processed_notes"
    notes.mkdir(parents=True, exist_ok=True)
    tags = extract_tags(text, cfg["tag_rules"])
    tpl = (vault / "templates" / "voice_note.md").read_text(encoding="utf-8")
    title = make_title(text)
    values = {
        "date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M"), "tags": ", ".join(tags),
        "due": extract_due(text, now), "title": title, "summary": make_summary(text), "text": text,
        "links": find_links(notes, tags),
    }
    for k, v in values.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    name = f"{now.strftime('%Y-%m-%d_%H%M')}_{slugify(title)}"
    out, n = notes / (name + ".md"), 2
    while out.exists():
        out, n = notes / f"{name}-{n}.md", n + 1
    out.write_text(tpl, encoding="utf-8", newline="\n")
    return out


def process_audio(path, cfg, now=None):
    now = now or dt.datetime.now()
    text = transcribe(path, cfg)
    if not text:
        print(f"Пустая расшифровка: {path.name} (файл оставлен в raw_inbox)")
        return None
    note = write_note(text, cfg, now)
    done = cfg["vault"] / "raw_inbox" / "done"
    done.mkdir(parents=True, exist_ok=True)
    if path.parent.resolve() == (cfg["vault"] / "raw_inbox").resolve():
        shutil.move(str(path), str(done / path.name))
    print(f"OK: {path.name} -> {note.name}")
    return note


# ---------- Telegram (длинный опрос; нужен токен в .env) ----------


def api(token, method, params=None, timeout=60):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=timeout) as r:
        return json.loads(r.read())


def poll(cfg, env):
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not token or token.startswith("PUT_"):
        sys.exit("Впишите токен бота (от BotFather) в файл .env: TELEGRAM_BOT_TOKEN=...")
    allowed = env.get("ALLOWED_CHAT_ID", "")
    inbox = cfg["vault"] / "raw_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    state = cfg["vault"] / ".bot_offset"
    offset = int(state.read_text()) if state.exists() else 0
    print("Бот слушает. Остановка: Ctrl+C")
    while True:
        try:
            res = api(token, "getUpdates", {"offset": offset, "timeout": 50}, timeout=70)
        except (urllib.error.URLError, TimeoutError) as e:
            print("Нет связи с Telegram, повтор:", e)
            continue
        for u in res.get("result", []):
            offset = u["update_id"] + 1
            state.write_text(str(offset))
            msg = u.get("message") or {}
            chat = str(msg.get("chat", {}).get("id", ""))
            if not allowed:
                print(f"ALLOWED_CHAT_ID не задан. Ваш chat id: {chat}. Впишите его в .env и перезапустите.")
                continue
            if chat != allowed:
                continue
            f = msg.get("voice") or msg.get("audio")
            if not f:
                continue
            info = api(token, "getFile", {"file_id": f["file_id"]})
            if not info.get("ok"):
                print("getFile не удался (возможно, файл слишком большой):", info.get("description"))
                continue
            fp = info["result"]["file_path"]
            target = inbox / f"{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}{Path(fp).suffix or '.ogg'}"
            with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{fp}", timeout=120) as r:
                target.write_bytes(r.read())
            note = process_audio(target, cfg)
            if note and cfg.get("reply_in_chat", True):
                api(token, "sendMessage", {"chat_id": chat, "text": f"Заметка сохранена: {note.name}"})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "config.example.json"))
    ap.add_argument("--env", default=str(HERE / ".env"))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", help="обработать один аудиофайл")
    g.add_argument("--process-inbox", action="store_true")
    g.add_argument("--poll", action="store_true")
    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.file:
        process_audio(Path(a.file), cfg)
    elif a.process_inbox:
        files = [p for p in sorted((cfg["vault"] / "raw_inbox").glob("*")) if p.suffix.lower() in AUDIO_EXT]
        print(f"Файлов в raw_inbox: {len(files)}")
        for p in files:
            process_audio(p, cfg)
    else:
        poll(cfg, load_env(a.env))


if __name__ == "__main__":
    main()

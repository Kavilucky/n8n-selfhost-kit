# -*- coding: utf-8 -*-
"""Расшифровка аудио и видео в текст на вашем компьютере, без интернета и без облака.

Использование:
    python transcribe.py запись.mp3 [ещё_файл.m4a ...]
    python transcribe.py запись.mp3 --model medium --lang auto

Результат рядом с файлом: <имя>.txt (текст) и <имя>.srt (субтитры с таймкодами).
Модель по умолчанию small: работает на обычном процессоре, без видеокарты.
При первом запуске модель скачивается один раз (small ~ 460 МБ), дальше работает офлайн.
"""
import argparse
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def stamp(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    ap = argparse.ArgumentParser(description="Расшифровка аудио/видео через faster-whisper")
    ap.add_argument("files", nargs="+", help="аудио или видеофайлы")
    ap.add_argument("--model", default="small", help="tiny, base, small, medium, large-v3 (по умолчанию small)")
    ap.add_argument("--lang", default="ru", help="язык записи: ru, en ... или auto (определить самому)")
    a = ap.parse_args()

    from faster_whisper import WhisperModel

    print(f"Загружаю модель {a.model} (при первом запуске скачивается один раз)...")
    model = WhisperModel(a.model, device="cpu", compute_type="int8")
    lang = None if a.lang == "auto" else a.lang
    bad = 0
    for f in a.files:
        src = Path(f)
        if not src.is_file():
            print(f"Нет файла: {src}")
            bad += 1
            continue
        t0 = time.time()
        print(f"\n{src.name}: расшифровываю...")
        try:
            segments, info = model.transcribe(str(src), language=lang, beam_size=5, vad_filter=True)
            txt, srt = [], []
            for i, s in enumerate(segments, 1):
                line = s.text.strip()
                txt.append(line)
                srt.append(f"{i}\n{stamp(s.start)} --> {stamp(s.end)}\n{line}\n")
                print(f"  {int(s.end):>5} с из {info.duration:.0f}", end="\r")
        except Exception as e:
            print(f"Не удалось прочитать {src.name}: {e}")
            bad += 1
            continue
        src.with_suffix(".txt").write_text("\n".join(txt) + "\n", encoding="utf-8")
        src.with_suffix(".srt").write_text("\n".join(srt), encoding="utf-8")
        print(f"Готово за {time.time() - t0:.0f} с: {src.with_suffix('.txt').name}, {src.with_suffix('.srt').name}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

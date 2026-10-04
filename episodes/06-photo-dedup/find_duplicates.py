# -*- coding: utf-8 -*-
"""Поиск визуальных дубликатов фотографий (pHash) с безопасным переносом в карантин.

Что делает: находит похожие картинки независимо от разрешения и степени сжатия (перцептивный хэш pHash:
уменьшение до 32x32, косинусное преобразование, 64 бита по низким частотам). Лишние копии НЕ удаляются:
они переносятся в папку _duplicates_quarantine внутри проверяемой папки, а в логе записано, откуда что взято.
Вернуть всё обратно можно командой --undo.

Использование:
    python find_duplicates.py ПАПКА                 показать найденное и спросить, переносить ли
    python find_duplicates.py ПАПКА --dry-run       только показать, ничего не трогать
    python find_duplicates.py ПАПКА --yes           перенести без вопроса
    python find_duplicates.py ПАПКА --threshold 8   строже/мягче (0..12, по умолчанию 6)
    python find_duplicates.py ПАПКА --undo          вернуть последний перенос обратно

Зависимости: Pillow и numpy (pillow-heif необязателен: добавляет чтение HEIC с iPhone).
"""
import argparse
import csv
import json
import os
import shutil
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF = True
except Exception:
    HEIF = False

Image.MAX_IMAGE_PIXELS = 400_000_000  # защита от «бомб» распаковки; больше этого файл будет пропущен
QUARANTINE = "_duplicates_quarantine"
EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
if HEIF:
    EXT |= {".heic", ".heif"}
SKIP_DIRS = {QUARANTINE.lower(), "$recycle.bin", "system volume information"}

N = 32
_k = np.arange(N)[:, None]
_n = np.arange(N)[None, :]
DCT = np.cos(np.pi * (2 * _n + 1) * _k / (2 * N))


def low_freq(path):
    """Низкие частоты картинки: (матрица 8x8 коэффициентов DCT, ширина, высота). Нужна и для хэша, и для наглядных схем."""
    with Image.open(path) as im:
        w, h = im.size  # настоящий размер до ускоренного чтения
        if im.getexif().get(0x0112, 1) in (5, 6, 7, 8):
            w, h = h, w  # снимок повёрнут меткой ориентации
        im.draft("L", (256, 256))  # ускорение для JPEG: сразу читаем уменьшенную копию
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            bg.alpha_composite(rgba)
            im = bg
        g = im.convert("L").resize((N, N), Image.LANCZOS)
    a = np.asarray(g, dtype=np.float64)
    return (DCT @ a @ DCT.T)[:8, :8], w, h


def bits_of(low):
    """64 бита: больше ли каждый коэффициент медианы (без постоянной составляющей)."""
    flat = low.flatten()
    return flat > np.median(flat[1:])


def phash(path):
    """Возвращает (хэш 64 бита как int, ширина, высота)."""
    low, w, h = low_freq(path)
    value = 0
    for bit in bits_of(low):
        value = (value << 1) | int(bit)
    return value, w, h


def hamming(a, b):
    return bin(a ^ b).count("1")


def scan(root, with_progress=True):
    files = []
    skipped = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in EXT:
                files.append(Path(dirpath) / fn)
            elif ext in {".heic", ".heif"}:
                skipped.append((Path(dirpath) / fn, "HEIC не читается: поставьте pillow-heif"))
    items = []
    for i, p in enumerate(files, 1):
        try:
            h, w, hh = phash(p)
            st = p.stat()
            items.append({"path": p, "hash": h, "w": w, "h": hh, "size": st.st_size, "mtime": st.st_mtime})
        except Exception as e:
            skipped.append((p, f"не удалось прочитать: {type(e).__name__}"))
        if with_progress and (i % 25 == 0 or i == len(files)):
            print(f"  прочитано {i} из {len(files)}", end="\r", flush=True)
    if with_progress and files:
        print()
    return items, skipped


def find_groups(items, threshold):
    """Группы похожих картинок. Быстрый отбор кандидатов по частям хэша (принцип Дирихле), затем точная проверка."""
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    bands = threshold + 1
    edges = [round(i * 64 / bands) for i in range(bands + 1)]
    seen = set()
    for b in range(bands):
        lo, hi = edges[b], edges[b + 1]
        mask = (1 << (hi - lo)) - 1
        buckets = {}
        for idx, it in enumerate(items):
            buckets.setdefault((it["hash"] >> lo) & mask, []).append(idx)
        for lst in buckets.values():
            for x in range(len(lst)):
                for y in range(x + 1, len(lst)):
                    i, j = lst[x], lst[y]
                    if (i, j) in seen:
                        continue
                    seen.add((i, j))
                    if hamming(items[i]["hash"], items[j]["hash"]) <= threshold:
                        parent[find(i)] = find(j)
    comps = {}
    for idx in range(n):
        comps.setdefault(find(idx), []).append(idx)
    groups = []
    for members in comps.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda k: (-(items[k]["w"] * items[k]["h"]), -items[k]["size"], items[k]["mtime"], len(str(items[k]["path"]))))
        keep = members[0]
        dups, loose = [], []
        for k in members[1:]:
            d = hamming(items[keep]["hash"], items[k]["hash"])
            (dups if d <= threshold else loose).append((k, d))
        if dups:
            groups.append({"keep": keep, "dups": dups, "loose": loose})
    groups.sort(key=lambda g: -sum(items[k]["size"] for k, _ in g["dups"]))
    return groups


def mb(n):
    return f"{n / 1048576:.1f} МБ" if n >= 1048576 else f"{n / 1024:.0f} КБ"


def unique_dest(dest):
    if not dest.exists():
        return dest
    stem, suf = dest.stem, dest.suffix
    c = 1
    while True:
        cand = dest.with_name(f"{stem}_{c}{suf}")
        if not cand.exists():
            return cand
        c += 1


def move_to_quarantine(root, items, groups, threshold):
    run = time.strftime("%Y%m%d-%H%M%S")
    qdir = Path(root) / QUARANTINE / run
    log = {"root": str(root), "created": run, "threshold": threshold, "groups": []}
    moved = 0
    freed = 0
    for gi, g in enumerate(groups, 1):
        keep = items[g["keep"]]
        entry = {"keep": str(keep["path"]), "moved": []}
        gdir = qdir / f"group_{gi:03d}"
        for k, d in g["dups"]:
            it = items[k]
            gdir.mkdir(parents=True, exist_ok=True)
            dest = unique_dest(gdir / it["path"].name)
            src = it["path"]
            size = src.stat().st_size
            shutil.move(str(src), str(dest))
            if not dest.exists() or dest.stat().st_size != size:
                raise RuntimeError(f"Проверка после переноса не прошла: {dest}")
            entry["moved"].append({"from": str(src), "to": str(dest), "distance": d})
            moved += 1
            freed += size
        log["groups"].append(entry)
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / "moves_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(qdir / "report.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["группа", "оставлен", "перенесён из", "перенесён в", "расстояние pHash"])
        for gi, e in enumerate(log["groups"], 1):
            for m in e["moved"]:
                w.writerow([gi, e["keep"], m["from"], m["to"], m["distance"]])
    return qdir, moved, freed


def undo(root, log_path=None):
    root = Path(root)
    if log_path is None:
        logs = sorted((root / QUARANTINE).glob("*/moves_log.json"))
        logs = [p for p in logs if not (p.parent / "undone.txt").exists()]
        if not logs:
            print("Нечего возвращать: не найдено ни одного неотменённого переноса.")
            return 1
        log_path = logs[-1]
    log_path = Path(log_path)
    log = json.loads(log_path.read_text(encoding="utf-8"))
    back = 0
    for g in log["groups"]:
        for m in g["moved"]:
            src, dst = Path(m["to"]), Path(m["from"])
            if not src.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst = unique_dest(dst) if dst.exists() else dst
            shutil.move(str(src), str(dst))
            back += 1
    (log_path.parent / "undone.txt").write_text(f"Возвращено файлов: {back}\n", encoding="utf-8")
    print(f"Возвращено файлов на прежние места: {back}. Журнал: {log_path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Поиск визуальных дубликатов фото (pHash), перенос в карантин без удаления")
    ap.add_argument("folder", help="папка с фотографиями (поиск идёт и во вложенных папках)")
    ap.add_argument("--threshold", type=int, default=6, help="допустимое расстояние pHash, 0..12 (по умолчанию 6; меньше - строже)")
    ap.add_argument("--dry-run", action="store_true", help="только показать найденное, файлы не трогать")
    ap.add_argument("--yes", action="store_true", help="не спрашивать подтверждение")
    ap.add_argument("--undo", action="store_true", help="вернуть последний перенос обратно")
    a = ap.parse_args()

    root = Path(a.folder)
    if not root.is_dir():
        print(f"Папка не найдена: {root}")
        return 2
    if a.undo:
        return undo(root)
    if not 0 <= a.threshold <= 12:
        print("--threshold должен быть от 0 до 12")
        return 2

    print(f"Папка: {root}")
    if not HEIF:
        print("Подсказка: файлы HEIC (фото с iPhone) будут пропущены. Чтобы их читать: pip install pillow-heif")
    t0 = time.time()
    items, skipped = scan(root)
    print(f"Картинок прочитано: {len(items)}, пропущено: {len(skipped)}, время {time.time() - t0:.1f} с")
    for p, why in skipped[:10]:
        print(f"  пропущен {p.name}: {why}")
    if len(skipped) > 10:
        print(f"  ... и ещё {len(skipped) - 10}")

    groups = find_groups(items, a.threshold)
    total_dups = sum(len(g["dups"]) for g in groups)
    total_size = sum(items[k]["size"] for g in groups for k, _ in g["dups"])
    if not groups:
        print("Дубликатов не найдено.")
        return 0
    print(f"\nГрупп похожих картинок: {len(groups)}; лишних копий: {total_dups}; можно освободить: {mb(total_size)}")
    for gi, g in enumerate(groups[:15], 1):
        keep = items[g["keep"]]
        print(f"\n  Группа {gi}: оставляем {keep['path'].name} ({keep['w']}x{keep['h']}, {mb(keep['size'])})")
        for k, d in g["dups"]:
            it = items[k]
            print(f"      копия {it['path'].name} ({it['w']}x{it['h']}, {mb(it['size'])}), расстояние {d}")
    if len(groups) > 15:
        print(f"\n  ... ещё групп: {len(groups) - 15} (полный список будет в report.csv после переноса)")
    loose = sum(len(g["loose"]) for g in groups)
    if loose:
        print(f"\nПограничных файлов, которые я НЕ трогаю: {loose} (слишком далеки от оригинала в группе)")

    if a.dry_run:
        print("\nРежим --dry-run: файлы не тронуты.")
        return 0
    if not a.yes:
        try:
            ans = input(f"\nПеренести {total_dups} копий ({mb(total_size)}) в папку {QUARANTINE}? Ничего не удаляется. [y/N]: ").strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("y", "yes", "д", "да"):
            print("Отменено, файлы не тронуты.")
            return 0
    qdir, moved, freed = move_to_quarantine(root, items, groups, a.threshold)
    print(f"\nПеренесено: {moved} файлов ({mb(freed)}). Карантин: {qdir}")
    print("Проверьте результат. Вернуть всё на место: python find_duplicates.py ПАПКА --undo")
    return 0


if __name__ == "__main__":
    sys.exit(main())

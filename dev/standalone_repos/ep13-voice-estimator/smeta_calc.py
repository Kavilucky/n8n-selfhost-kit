#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""smeta_calc.py: голос или текст замеров -> ориентировочная смета (HTML, при возможности PDF). Всё считается на вашем компьютере.

Как работает:
  1. Запись (ogg, mp3, m4a, wav) превращается в текст локальным Whisper (пакет faster-whisper); либо вы даёте готовый текст через --text.
  2. Правила разбора режут текст на фразы и достают из каждой название, количество и единицу измерения.
  3. Позиция ищется в прайс-листе (обычный файл Excel .xlsx, колонки: Название, Синонимы, Единица, Цена).
  4. Сумма = количество x цена, итог = сумма позиций. Позиции без цены в прайсе помечаются «нет в прайсе», цена НЕ придумывается и в итог не входит.
  5. Шаблон estimate.html (Jinja2, автоэкранирование включено) собирает страницу; PDF создаётся через WeasyPrint, если он установлен,
     иначе откройте HTML в браузере и сохраните как PDF (Ctrl+P).

Скрипт ничего не отправляет в сеть. Единственное исключение: при первом запуске с записью faster-whisper скачивает модель.
Смета ориентировочная: не договор, не акт, не нормативная форма, налоги не считаются. Проверьте позиции, количества и цены.

Примеры:
  python smeta_calc.py --text "стена три двадцать, розеток пять, плитки шесть квадратов"
  python smeta_calc.py запись.ogg --price мой_прайс.xlsx --title "Смета, квартира на Лесной"
Код возврата: 0 всё сопоставлено, 1 есть позиции «нет в прайсе» или без количества, 2 ошибка.
"""
import argparse
import datetime
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
NBSP = " "

# ---------------------------------------------------------------- числа словами
UNITS = {"ноль": 0, "один": 1, "одна": 1, "одну": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9}
TEENS = {"десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19}
TENS = {"двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90}
HUNDREDS = {"сто": 100, "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900}
SPECIAL = {"полтора": Decimal("1.5"), "полторы": Decimal("1.5")}
STOP = {"на", "в", "по", "и", "у", "с", "со", "еще", "около", "примерно", "где", "там", "нужно", "надо", "сделать", "сделай", "добавь", "добавить", "позиция", "пункт", "погонных", "погонный", "погонных"}
UNIT_SQ = {"кв", "квм", "м2", "м²", "квадрат", "квадраты", "квадрата", "квадратов", "квадратных", "квадратный", "квадратных"}


def numclass(w):
    """(класс, значение, метка): сотни 3, десятки и 11-19 класс 2, единицы 1; иначе None."""
    if w in HUNDREDS:
        return (3, HUNDREDS[w], "hund")
    if w in TENS:
        return (2, TENS[w], "tens")
    if w in TEENS:
        return (2, TEENS[w], "teen")
    if w in UNITS:
        return (1, UNITS[w], "unit")
    return None


def tokenize(text):
    return re.findall(r"\d+(?:[.,]\d+)?|[а-яa-z]+[2²]?|²", text.lower().replace("ё", "е"))


def parse_numbers(words):
    """Список элементов: ('num', Decimal, 'digit'|'word') или ('word', слово). Составные числа словами собираются жадно:
    «двадцать пять» это 25, «сто двадцать» это 120, а «три двадцать» это два числа (потом склеиваются в 3,20)."""
    out, i = [], 0
    while i < len(words):
        w = words[i]
        if re.fullmatch(r"\d+(?:[.,]\d+)?", w):
            out.append(("num", Decimal(w.replace(",", ".")), "digit", w)); i += 1; continue
        if w in SPECIAL:
            out.append(("num", SPECIAL[w], "word")); i += 1; continue
        if numclass(w):
            val, last, j = 0, 4, i
            while j < len(words):
                c = numclass(words[j])
                if not c or c[0] >= last:
                    break
                val += c[1]; last = c[0]; j += 1
                if c[2] == "teen":
                    break
            out.append(("num", Decimal(val), "word")); i = j; continue
        out.append(("word", w)); i += 1
    merged, k = [], 0
    while k < len(out):
        a = out[k]
        b = out[k + 1] if k + 1 < len(out) else None
        # Whisper часто пишет «три двадцать» цифрами: «3-20» или «3 20» (два целых подряд, второе из двух цифр) -> тоже 3,20
        if a[0] == "num" and b and b[0] == "num" and a[2] == "digit" and b[2] == "digit" and a[3].isdigit() and b[3].isdigit() and len(b[3]) == 2 and 1 <= a[1] <= 99:
            merged.append(("num", a[1] + b[1] / Decimal(100), "digit", "")); k += 2; continue
        # «три двадцать» -> 3,20 (метры и сантиметры): два числа словами подряд, второе от 10 до 99
        if a[0] == "num" and b and b[0] == "num" and a[2] == "word" and b[2] == "word" and a[1] == a[1].to_integral() and Decimal(10) <= b[1] <= Decimal(99):
            merged.append(("num", a[1] + b[1] / Decimal(100), "word")); k += 2
        else:
            merged.append(a); k += 1
    return merged


def stem(w):
    w = w.replace("ё", "е")
    return w[:max(4, len(w) - 2)] if len(w) > 4 else w


def split_phrases(text):
    parts = re.split(r"[;\n]+|(?<!\d)[.,]|[.,](?!\d)", text)
    return [p.strip() for p in parts if p and p.strip()]


def parse_phrase(phrase):
    items = parse_numbers(tokenize(phrase))
    nums = [x for x in items if x[0] == "num"]
    words = [x[1] for x in items if x[0] == "word"]
    unit = None
    if any(w in UNIT_SQ or w.startswith("квадрат") for w in words):
        unit = "м²"
    elif any(w == "м" or w.startswith("метр") for w in words):
        unit = "м"
    elif any(w == "шт" or w.startswith("штук") for w in words):
        unit = "шт"
    name_words = [w for w in words if w not in STOP and w not in UNIT_SQ and not w.startswith("квадрат") and w != "м" and not w.startswith("метр") and w != "шт" and not w.startswith("штук")]
    notes = []
    if len(nums) > 1:
        notes.append("в фразе несколько чисел, использовано первое")
    return {"phrase": phrase, "name_words": name_words, "qty": nums[0][1] if nums else None, "unit": unit, "notes": notes}


# ---------------------------------------------------------------- прайс-лист .xlsx без сторонних библиотек
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
MAX_PART = 20 * 1024 * 1024


def _part(z, name):
    info = z.getinfo(name)
    if info.file_size > MAX_PART:
        raise ValueError(f"часть файла {name} слишком большая: файл не похож на обычный прайс-лист")
    return z.read(name)


def _col_index(ref):
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx_rows(path):
    """Строки первого листа как списки строк-значений (None для пустых). Читаются сохранённые значения ячеек; формулы не вычисляются."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(_part(z, "xl/sharedStrings.xml")).findall(M + "si"):
                shared.append("".join(t.text or "" for t in si.iter(M + "t")))
        wb = ET.fromstring(_part(z, "xl/workbook.xml"))
        first = wb.find(M + "sheets").find(M + "sheet")
        rid = first.get(R + "id")
        rels = ET.fromstring(_part(z, "xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels if r.get("Id") == rid)
        sheet = target.lstrip("/") if target.startswith("/") else "xl/" + target
        root = ET.fromstring(_part(z, sheet))
        rows = []
        for row in root.iter(M + "row"):
            cells = {}
            for c in row.findall(M + "c"):
                t, v, f = c.get("t"), c.find(M + "v"), c.find(M + "f")
                if t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(M + "t"))
                elif v is None or v.text is None:
                    val = "#ФОРМУЛА" if f is not None else None
                elif t == "s":
                    val = shared[int(v.text)]
                elif t == "e":
                    val = "#ОШИБКА"
                else:
                    val = v.text
                cells[_col_index(c.get("r"))] = val
            rows.append([cells.get(i) for i in range(max(cells) + 1)] if cells else [])
        return rows


HEADS = {"name": ("название", "позиция", "наименование"), "syn": ("синонимы", "как говорят"), "unit": ("единица", "ед", "ед.", "ед. изм."), "price": ("цена", "цена, ₽", "цена, руб", "цена за единицу")}


def load_price(path):
    """-> (список позиций, предупреждения). Позиция: name, unit, price (Decimal), keys (списки основ слов для поиска)."""
    path = Path(path)
    if not path.exists():
        raise ValueError(f"нет файла прайс-листа: {path}")
    rows = read_xlsx_rows(path)
    if not rows:
        raise ValueError("прайс-лист пуст")
    head = [str(x or "").strip().lower() for x in rows[0]]
    col = {}
    for key, variants in HEADS.items():
        for i, h in enumerate(head):
            if h in variants:
                col[key] = i; break
    for need in ("name", "unit", "price"):
        if need not in col:
            raise ValueError("в первой строке прайса нужны колонки: Название, Синонимы (необязательно), Единица, Цена")
    items, warns, seen = [], [], {}
    for n, r in enumerate(rows[1:], start=2):
        def cell(k):
            i = col.get(k)
            return r[i] if i is not None and i < len(r) else None
        name = (cell("name") or "").strip()
        if not name:
            continue
        raw = cell("price")
        if raw == "#ФОРМУЛА":
            raise ValueError(f"строка {n}: цена задана формулой без сохранённого значения; откройте файл в Excel, сохраните и повторите, либо впишите число")
        try:
            price = Decimal(re.sub(r"[\s ₽]|руб\.?", "", str(raw)).replace(",", "."))
        except (InvalidOperation, TypeError):
            raise ValueError(f"строка {n}: цена «{raw}» не число; впишите число без знака валюты")
        if price < 0:
            raise ValueError(f"строка {n}: цена отрицательная")
        syns = [name] + [s.strip() for s in re.split(r"[,;/]", str(cell("syn") or "")) if s.strip()]
        keys = []
        for s in syns:
            ks = tuple(stem(w) for w in tokenize(s) if w not in STOP)
            if ks:
                keys.append(ks)
                if ks in seen and seen[ks] != name:
                    warns.append(f"позиции «{seen[ks]}» и «{name}» имеют одинаковый поисковый ключ «{' '.join(ks)}»: запись будет сопоставляться с первой")
                seen.setdefault(ks, name)
        items.append({"name": name, "unit": str(cell("unit") or "").strip(), "price": price, "keys": keys})
    if not items:
        raise ValueError("в прайс-листе нет позиций")
    return items, warns


def match(item_words, price):
    stems = {stem(w) for w in item_words}
    best, score = None, 0
    for it in price:
        for ks in it["keys"]:
            if set(ks) <= stems and len(ks) > score:
                best, score = it, len(ks)
    return best


# ---------------------------------------------------------------- расчёт и формат
def money(d):
    d = d.quantize(Decimal("0.01"), ROUND_HALF_UP)
    if d == d.to_integral():
        s = f"{int(d):,}".replace(",", NBSP)
    else:
        s = f"{d:,.2f}".replace(",", NBSP).replace(".", ",")
    return s + NBSP + "₽"


def qty_str(q):
    return str(int(q)) if q == q.to_integral() else f"{q:.2f}".replace(".", ",")


def build_estimate(text, price):
    rows, total, bad = [], Decimal(0), 0
    for ph in split_phrases(text):
        p = parse_phrase(ph)
        notes = list(p["notes"])
        it = match(p["name_words"], price) if p["name_words"] else None
        heard = " ".join(p["name_words"]) or "(название не распознано)"
        row = {"heard": ph, "name": it["name"] if it else heard.capitalize(), "qty": qty_str(p["qty"]) if p["qty"] is not None else "—", "unit": p["unit"] or (it["unit"] if it else ""), "price": "—", "sum": "—", "status": "ok", "notes": notes}
        if it is None:
            row["status"] = "noprice"; row["price"] = "нет в прайсе"; bad += 1
        else:
            row["price"] = money(it["price"])
            if p["unit"] and it["unit"] and p["unit"] != it["unit"]:
                notes.append(f"единица в записи ({p['unit']}) не совпадает с прайсом ({it['unit']}): проверьте")
            elif not p["unit"] and it["unit"]:
                notes.append(f"единица взята из прайса ({it['unit']})")
            if p["qty"] is None:
                row["status"] = "noqty"; row["sum"] = "нет количества"; bad += 1
            else:
                s = (p["qty"] * it["price"]).quantize(Decimal("0.01"), ROUND_HALF_UP)
                row["sum"] = money(s); total += s
        rows.append(row)
    return rows, total, bad


def transcribe(path, model_name):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit("Для разбора записи нужен пакет faster-whisper: pip install faster-whisper. Либо передайте текст через --text.")
    print("Загружаю модель Whisper: при первом запуске она скачивается из интернета, дальше работает без сети...")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(path), language="ru", beam_size=5)
    return " ".join(s.text.strip() for s in segments).strip()


def render_html(template_path, ctx):
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError:
        raise SystemExit("Нужен пакет Jinja2: pip install Jinja2")
    template_path = Path(template_path)
    env = Environment(loader=FileSystemLoader(str(template_path.parent)), autoescape=True)  # текст расшифровки попадает в HTML: экранирование обязательно
    return env.get_template(template_path.name).render(**ctx)


def write_pdf(html_text, html_path, pdf_path):
    try:
        from weasyprint import HTML
        HTML(string=html_text, base_url=str(html_path.parent)).write_pdf(str(pdf_path))
        return True
    except (ImportError, OSError):
        return False


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Голос или текст замеров -> ориентировочная смета (HTML и PDF).")
    ap.add_argument("audio", nargs="?", help="файл записи (ogg, mp3, m4a, wav)")
    ap.add_argument("--text", help="готовый текст вместо записи, например: \"стена три двадцать, розеток пять\"")
    ap.add_argument("--text-file", help="текстовый файл с замерами")
    ap.add_argument("--price", default=str(HERE / "price_list_template.xlsx"), help="прайс-лист .xlsx (по умолчанию образец рядом со скриптом)")
    ap.add_argument("--template", default=str(HERE / "estimate.html"), help="шаблон сметы Jinja2")
    ap.add_argument("--out", help="путь к HTML-смете (по умолчанию сметы/smeta_ДАТА.html)")
    ap.add_argument("--title", default="Смета (ориентировочная)")
    ap.add_argument("--model", default="small", help="модель Whisper: tiny, base, small (по умолчанию), medium")
    ap.add_argument("--no-pdf", action="store_true", help="не пытаться создать PDF")
    ap.add_argument("--date", help="дата в смете (по умолчанию сегодня)")
    a = ap.parse_args(argv)
    sources = [bool(a.audio), a.text is not None, bool(a.text_file)]
    if sum(sources) != 1:
        print("Укажите ровно один источник: файл записи, --text или --text-file.", file=sys.stderr)
        return 2
    try:
        price, warns = load_price(a.price)
        if a.audio:
            if not Path(a.audio).exists():
                raise ValueError(f"нет файла записи: {a.audio}")
            text = transcribe(a.audio, a.model)
        elif a.text_file:
            text = Path(a.text_file).read_text(encoding="utf-8")
        else:
            text = a.text
        if not text.strip():
            raise ValueError("текст пуст: запись не распознана или файл пустой")
        rows, total, bad = build_estimate(text, price)
        if not rows:
            raise ValueError("в тексте не нашлось ни одной фразы")
        date = a.date or datetime.date.today().strftime("%d.%m.%Y")
        html_text = render_html(a.template, {"title": a.title, "date": date, "rows": rows, "total": money(total), "n_bad": bad, "phrases": split_phrases(text), "warnings": warns})
    except (ValueError, OSError, zipfile.BadZipFile, ET.ParseError, KeyError, StopIteration) as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 2
    out = Path(a.out) if a.out else HERE / "сметы" / ("smeta_" + datetime.datetime.now().strftime("%Y-%m-%d_%H%M") + ".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8", newline="\n")
    print("Расшифровка:", text.strip())
    print()
    for i, r in enumerate(rows, 1):
        print(f"{i}. {r['name']}: {r['qty']} {r['unit']}, цена {r['price']}, сумма {r['sum']}".replace(NBSP, " "))
        for n in r["notes"]:
            print("     ! " + n)
    print(f"ИТОГО: {money(total)}".replace(NBSP, " "), "(позиции без цены в итог не входят)" if bad else "")
    for w in warns:
        print("Предупреждение:", w)
    print("Смета ориентировочная: сверьте позиции, количества и цены перед отправкой клиенту.")
    print("HTML:", out)
    if not a.no_pdf:
        pdf = out.with_suffix(".pdf")
        if write_pdf(html_text, out, pdf):
            print("PDF:", pdf)
        else:
            print("PDF не создан (WeasyPrint не установлен или не нашёл системные библиотеки). Откройте HTML в браузере и сохраните как PDF: Ctrl+P.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

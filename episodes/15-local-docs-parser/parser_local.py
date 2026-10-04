#!/usr/bin/env python3
"""Локальный парсер актов и первички: PDF в Excel без отправки данных в сеть.

Что делает: берёт папку с PDF (акты выполненных работ, оказания услуг), достаёт текстовый слой (PyMuPDF), находит реквизиты правилами
(ИНН и КПП исполнителя и заказчика, номер акта, дата, сумма без НДС, НДС, итого), проверяет их (контрольная сумма ИНН, формат КПП, сумма = без НДС + НДС)
и пишет реестр в .xlsx (и .csv). Если правила не нашли поле или проверка не прошла, спрашивает ЛОКАЛЬНУЮ модель Ollama (только на этом компьютере),
а ответ принимает лишь после той же проверки и только если значение буквально есть в тексте документа (защита от «придуманных» цифр).

Сеть: скрипт сам блокирует любые соединения, кроме 127.0.0.1 / localhost (см. block_network): ни реквизиты, ни суммы, ни тексты не могут уйти наружу.
Ограничения: PDF без текстового слоя (сканы) не распознаются (v1 без OCR, строка помечается «скан»); облачные модели Ollama запрещены проверкой.
Запуск: python parser_local.py <папка_с_PDF> [--out реестр.xlsx] [--model qwen2.5:3b] [--no-llm]
"""
import argparse
import csv
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.request
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.sax.saxutils import escape

OLLAMA_DEFAULT = "http://127.0.0.1:11434"
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}
MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}
COLUMNS = ["Файл", "Номер акта", "Дата", "ИНН исполнителя", "КПП исполнителя", "ИНН заказчика", "КПП заказчика", "Сумма без НДС", "НДС", "Итого", "Метод", "Проверка", "Замечания"]
NUM = r"\d{1,3}(?:[\s  ]?\d{3})*(?:[.,]\d{2})"


# ---------- защита от выхода в сеть ----------
def _is_local(host):
    if host is None:
        return False
    host = str(host).strip("[]").lower()
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def block_network():
    """Запрещает соединения и DNS-запросы наружу: разрешён только loopback. Вызывается до любой работы с файлами."""
    orig_connect, orig_connect_ex, orig_gai = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo

    def _check(sock, address):
        if getattr(sock, "family", None) == getattr(socket, "AF_UNIX", -1):
            return
        host = address[0] if isinstance(address, tuple) else address
        if not _is_local(host):
            raise PermissionError(f"сетевое соединение запрещено (разрешён только локальный адрес): {host}")

    def connect(self, address):
        _check(self, address)
        return orig_connect(self, address)

    def connect_ex(self, address):
        _check(self, address)
        return orig_connect_ex(self, address)

    def getaddrinfo(host, *a, **kw):
        if not _is_local(host):
            raise PermissionError(f"DNS-запрос наружу запрещён: {host}")
        return orig_gai(host, *a, **kw)

    socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo


# ---------- проверки реквизитов ----------
def inn_ok(s):
    """Контрольная сумма ИНН (10 цифр для организаций, 12 для ИП и физлиц)."""
    if not re.fullmatch(r"\d{10}|\d{12}", s or ""):
        return False
    d = [int(c) for c in s]
    if len(d) == 10:
        w = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        return sum(a * b for a, b in zip(w, d)) % 11 % 10 == d[9]
    w1, w2 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8], [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    return sum(a * b for a, b in zip(w1, d)) % 11 % 10 == d[10] and sum(a * b for a, b in zip(w2, d)) % 11 % 10 == d[11]


def kpp_ok(s):
    return bool(re.fullmatch(r"\d{4}[0-9A-Z]{2}\d{3}", s or ""))


def to_dec(s):
    if s is None:
        return None
    raw = re.sub(r"[\s  ]", "", str(s))
    m = re.fullmatch(r"(\d[\d.,]*?)[.,](\d{2})", raw)   # последняя точка или запятая с двумя цифрами = копейки, остальные разделители тысяч убираются
    if m:
        raw = re.sub(r"[.,]", "", m.group(1)) + "." + m.group(2)
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None


def fmt_money(d):
    return None if d is None else float(d)


def norm_date(day, month, year):
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


# ---------- извлечение правилами ----------
def parse_rules(text):
    """Возвращает словарь полей (None, если поле не найдено)."""
    t = text.replace(" ", " ").replace(" ", " ")
    f = {k: None for k in ("act_number", "act_date", "exec_inn", "exec_kpp", "cust_inn", "cust_kpp", "net", "vat", "total")}
    m = re.search(r"(?:Акт[^\n№Nn]{0,60})(?:№|N|No)\s*([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9/\-_.]{0,19})", t, re.I)
    if m:
        f["act_number"] = m.group(1).rstrip(".")
    m = re.search(r"от\s*[«\"]?(\d{1,2})[»\"]?\s+([а-яё]+)\s+(\d{4})", t, re.I)
    if m and m.group(2).lower() in MONTHS:
        f["act_date"] = norm_date(m.group(1), MONTHS[m.group(2).lower()], m.group(3))
    if not f["act_date"]:
        m = re.search(r"(?:Дата[^\d\n]{0,12}|от\s+)(\d{2})\.(\d{2})\.(\d{4})", t)
        if m:
            f["act_date"] = norm_date(m.group(1), m.group(2), m.group(3))
    if not f["act_date"]:   # «(15 марта 2026)» без слова «от»
        m = re.search(r"(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})", t, re.I)
        if m:
            f["act_date"] = norm_date(m.group(1), MONTHS[m.group(2).lower()], m.group(3))
    # стороны: сегмент от слова «Исполнитель» до «Заказчик» и наоборот
    pe = re.search(r"Исполнитель", t)
    pc = re.search(r"Заказчик", t)
    segs = {}
    if pe and pc:
        a, b = sorted([(pe.start(), "exec"), (pc.start(), "cust")])
        end_mark = re.search(r"(?:№\s*п/п|Наименование|Основание|Услуги|Перечень)", t[b[0]:])
        segs[a[1]] = t[a[0]:b[0]]
        segs[b[1]] = t[b[0]: b[0] + (end_mark.start() if end_mark else 400)]
    for who, seg in segs.items():
        m = re.search(r"ИНН\s*/\s*КПП\s*[:№]?\s*(\d{10,12})\s*/\s*(\d{9})", seg)
        if m:
            f[who + "_inn"], f[who + "_kpp"] = m.group(1), m.group(2)
            continue
        m = re.search(r"ИНН[\s:№]*(\d{10,12})", seg)
        f[who + "_inn"] = m.group(1) if m else None
        m = re.search(r"КПП[\s:№]*([0-9A-Z]{9})", seg)
        f[who + "_kpp"] = m.group(1) if m else None
    # суммы
    m = re.search(r"(?:Сумма|Итого|Стоимость)\s+без\s+НДС[^\d\n]{0,25}(" + NUM + ")", t, re.I)
    if m:
        f["net"] = to_dec(m.group(1))
    vats = [x for x in re.finditer(r"(?<!без\s)(?<!с\s)НДС(?:\s*\(?\d{1,2}\s*%\)?)?[^\d\n]{0,25}(" + NUM + ")", t, re.I)]
    if vats:
        f["vat"] = to_dec(vats[-1].group(1))
    elif re.search(r"НДС\s+не\s+облагается|без\s+НДС\s*\)", t, re.I):
        f["vat"] = Decimal("0.00")
    tot = list(re.finditer(r"(?:Итого(?!\s+без)(?:\s+к\s+оплате|\s+с\s+НДС)?|Всего\s+к\s+оплате)[^\d\n]{0,25}(" + NUM + ")", t, re.I))
    if tot:
        f["total"] = to_dec(tot[-1].group(1))
    if f["net"] is None and f["vat"] == Decimal("0.00") and f["total"] is not None:
        f["net"] = f["total"]
    return f


def derive_net(f):
    """Сумма без НДС = итого минус НДС, если её нет в тексте, но есть обе суммы. Возвращает True, если посчитано."""
    if f["net"] is None and f["total"] is not None and f["vat"] is not None:
        f["net"] = f["total"] - f["vat"]
        return True
    return False


def validate(f):
    """Список замечаний (пусто = всё сошлось)."""
    w = []
    for who, label in (("exec", "исполнителя"), ("cust", "заказчика")):
        i, k = f[who + "_inn"], f[who + "_kpp"]
        if i is None:
            w.append(f"нет ИНН {label}")
        elif not inn_ok(i):
            w.append(f"ИНН {label} {i}: контрольная сумма не сходится (опечатка?)")
        if k is not None and not kpp_ok(k):
            w.append(f"КПП {label} {k}: неверный формат")
    for key, label in (("act_number", "номер акта"), ("act_date", "дата"), ("net", "сумма без НДС"), ("total", "итого")):
        if f[key] is None:
            w.append(f"нет поля: {label}")
    if f["net"] is not None and f["total"] is not None and f["vat"] is not None:
        if abs(f["net"] + f["vat"] - f["total"]) > Decimal("0.01"):
            w.append(f"сумма не сходится: {f['net']} + НДС {f['vat']} != итого {f['total']}")
    return w


# ---------- локальная модель Ollama ----------
SCHEMA = {"type": "object", "properties": {k: {"type": ["string", "null"]} for k in
          ("act_number", "act_date", "exec_inn", "exec_kpp", "cust_inn", "cust_kpp", "net", "vat", "total")}, "required": []}


def ollama_json(host, path, payload=None, timeout=120):
    req = urllib.request.Request(host + path, data=None if payload is None else json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check_model_is_local(host, model):
    """Облачные модели Ollama отправляют запросы на серверы Ollama: отказываемся от них. Возвращает текст ошибки или None."""
    if model.lower().endswith("cloud"):
        return f"модель {model} облачная: запрещена"
    tags = ollama_json(host, "/api/tags", timeout=10).get("models", [])
    for m in tags:
        if m.get("name") == model or m.get("model") == model:
            if any("remote" in k.lower() for k in m) or not m.get("size"):
                return f"модель {model} выглядит облачной (удалённая или без локальных весов): запрещена"
            return None
    return f"модель {model} не найдена локально (ollama pull {model}, нужен интернет один раз)"


def llm_fields(host, model, text):
    prompt = ("Ты разбираешь российский акт выполненных работ или оказания услуг. Верни ТОЛЬКО JSON по схеме. "
              "Поля: act_number (номер акта), act_date (дата акта в формате ГГГГ-ММ-ДД), exec_inn и exec_kpp (ИНН и КПП исполнителя), "
              "cust_inn и cust_kpp (ИНН и КПП заказчика), "
              "total (ОБЩАЯ сумма акта с НДС: слова «всего», «итого», «на сумму», «к оплате»), vat (сумма НДС в рублях, не процент), "
              "net (сумма БЕЗ НДС, только если она явно указана в тексте, иначе null). "
              "Суммы пиши как в тексте, например 344 129,16. Если поля нет в тексте, поставь null. Ничего не выдумывай и не считай: копируй цифры из текста.\n\nТЕКСТ АКТА:\n" + text[:6000])
    r = ollama_json(host, "/api/chat", {"model": model, "stream": False, "format": SCHEMA, "options": {"temperature": 0},
                                        "messages": [{"role": "user", "content": prompt}]})
    return json.loads(r["message"]["content"])


def digits(s):
    return re.sub(r"\D", "", str(s))


def accept_llm(f, llm, text):
    """Подставляет значения модели в пустые или неверные поля, только если цифры буквально есть в тексте и проверка проходит."""
    flat = re.sub(r"[\s  ]", "", text)
    used = []
    for who in ("exec", "cust"):
        for key, ok in ((who + "_inn", inn_ok), (who + "_kpp", kpp_ok)):
            v = str(llm.get(key) or "").strip()
            bad = f[key] is None or (key.endswith("inn") and not inn_ok(f[key]))
            if bad and v and ok(v) and v in flat:
                f[key] = v; used.append(key)
    v = str(llm.get("act_number") or "").strip()
    if f["act_number"] is None and v and v in text:
        f["act_number"] = v; used.append("act_number")
    v = str(llm.get("act_date") or "").strip()
    if f["act_date"] is None and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        y, mo, d = v.split("-")
        if d.lstrip("0") in text and y in text:
            f["act_date"] = v; used.append("act_date")
    for key in ("net", "vat", "total"):
        mm = re.search(NUM, str(llm.get(key) or "").replace(" ", " "))   # маленькие модели иногда пишут сумму целой фразой: берём первое число
        d = to_dec(mm.group(0)) if mm else None
        if f[key] is None and d is not None:
            raw = f"{d:.2f}"
            whole, frac = raw.split(".")
            if (whole + "," + frac) in flat or (whole + "." + frac) in flat or digits(raw) in digits(text):
                f[key] = d; used.append(key)
    return used


# ---------- обработка папки ----------
def read_pdf_text(path, max_pages=20):
    import pymupdf  # PyMuPDF (лицензия AGPL или коммерческая: см. Инструкцию)
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for i, page in enumerate(doc) if i < max_pages)


def process_pdf(path, use_llm, host, model):
    row = {c: None for c in COLUMNS}
    row["Файл"] = path.name
    try:
        text = read_pdf_text(path)
    except Exception as e:
        row["Проверка"], row["Замечания"], row["Метод"] = "ошибка", f"не удалось открыть PDF: {e}", "-"
        return row
    if len(text.strip()) < 30:
        row["Проверка"], row["Метод"] = "скан", "-"
        row["Замечания"] = "нет текстового слоя (скан или картинка): v1 без OCR, разберите вручную или используйте vision-модель"
        return row
    f = parse_rules(text)
    derived = derive_net(f)
    method, warns = "правила", validate(f)
    if warns and use_llm:
        try:
            used = accept_llm(f, llm_fields(host, model, text), text)
            if used:
                method = "правила + локальная модель"
            derived = derive_net(f) or derived
            warns = validate(f)
        except Exception as e:
            warns.append(f"локальная модель недоступна: {e}")
    row.update({"Номер акта": f["act_number"], "Дата": f["act_date"], "ИНН исполнителя": f["exec_inn"], "КПП исполнителя": f["exec_kpp"],
                "ИНН заказчика": f["cust_inn"], "КПП заказчика": f["cust_kpp"], "Сумма без НДС": fmt_money(f["net"]), "НДС": fmt_money(f["vat"]),
                "Итого": fmt_money(f["total"]), "Метод": method, "Проверка": "OK" if not warns else "проверить",
                "Замечания": "; ".join(warns + (["сумма без НДС рассчитана как итого минус НДС"] if derived else []))})
    return row


# ---------- запись Excel и CSV ----------
def write_csv(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in COLUMNS])


def write_xlsx(rows, path):
    """openpyxl, если установлен; иначе встроенная запись .xlsx (zipfile + XML) без сторонних пакетов."""
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Акты"
        ws.append(COLUMNS)
        for r in rows:
            ws.append([r[c] for c in COLUMNS])
        for i, wdt in enumerate([26, 14, 12, 16, 12, 16, 12, 16, 12, 16, 22, 12, 60], start=1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = wdt
        wb.save(path)
        return "openpyxl"
    except ImportError:
        pass
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    col = lambda i: chr(65 + i)
    srows = []
    for n, vals in enumerate([COLUMNS] + [[r[c] for c in COLUMNS] for r in rows], start=1):
        cells = []
        for i, v in enumerate(vals):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                cells.append(f'<c r="{col(i)}{n}"><v>{v}</v></c>')
            else:
                cells.append(f'<c r="{col(i)}{n}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>')
        srows.append(f'<row r="{n}">{"".join(cells)}</row>')
    sheet = xml + f'<worksheet xmlns="{ns}"><sheetData>' + "".join(srows) + "</sheetData></worksheet>"
    files = {
        "[Content_Types].xml": xml + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": xml + f'<Relationships xmlns="{pkg}"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": xml + f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets><sheet name="Акты" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": xml + f'<Relationships xmlns="{pkg}"><Relationship Id="rId1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files.items():
            z.writestr(n, d.encode("utf-8"))
    return "встроенная запись"


def selftest_network():
    """Пробует выйти наружу и убеждается, что соединение заблокировано (без реальной отправки данных)."""
    for target in (("1.1.1.1", 53), ("example.com", 80)):
        try:
            socket.create_connection(target, timeout=2)
            print(f"ОШИБКА: соединение с {target[0]} не заблокировано")
            return 1
        except PermissionError as e:
            print("заблокировано:", e)
    print("Проверка пройдена: наружу выйти нельзя, разрешён только локальный адрес.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Локальный парсер актов: PDF в Excel без отправки данных в сеть")
    ap.add_argument("folder", nargs="?", help="папка с PDF")
    ap.add_argument("--out", help="файл реестра .xlsx (по умолчанию реестр_актов.xlsx в этой папке)")
    ap.add_argument("--model", default="qwen2.5:3b", help="локальная модель Ollama для сложных документов")
    ap.add_argument("--host", default=OLLAMA_DEFAULT, help="адрес Ollama (только локальный)")
    ap.add_argument("--no-llm", action="store_true", help="только правила, без модели (самый быстрый режим)")
    ap.add_argument("--selftest-network", action="store_true", help="проверить, что скрипт не может выйти в сеть")
    a = ap.parse_args(argv)
    block_network()
    if a.selftest_network:
        return selftest_network()
    if not a.folder:
        ap.error("укажите папку с PDF")
    folder = Path(a.folder)
    pdfs = sorted(folder.glob("*.pdf")) + sorted(folder.glob("*.PDF"))
    pdfs = sorted(set(pdfs))
    if not pdfs:
        print("В папке нет PDF-файлов:", folder)
        return 2
    use_llm = not a.no_llm
    if use_llm:
        m = re.match(r"https?://([^:/]+)", a.host)
        if not m or not _is_local(m.group(1)):
            print("ОШИБКА: адрес Ollama должен быть локальным (127.0.0.1 или localhost), указан:", a.host)
            return 2
        try:
            err = check_model_is_local(a.host, a.model)
        except Exception as e:
            err = f"Ollama не отвечает на {a.host}: {e}"
        if err:
            print("Локальная модель отключена:", err, "\nПродолжаю только правилами (--no-llm).")
            use_llm = False
    t0 = time.perf_counter()
    rows = []
    for i, p in enumerate(pdfs, 1):
        r = process_pdf(p, use_llm, a.host, a.model)
        rows.append(r)
        print(f"[{i}/{len(pdfs)}] {p.name}: {r['Проверка']}" + (f" ({r['Замечания']})" if r["Замечания"] else ""))
    dt = time.perf_counter() - t0
    out = Path(a.out) if a.out else folder / "реестр_актов.xlsx"
    how = write_xlsx(rows, out)
    write_csv(rows, out.with_suffix(".csv"))
    ok = sum(1 for r in rows if r["Проверка"] == "OK")
    print(f"\nГотово: {len(rows)} файлов за {dt:.1f} с, без замечаний {ok}, проверить {len(rows) - ok}.\nРеестр: {out} ({how}) и {out.with_suffix('.csv').name}\n"
          "Все данные обработаны на этом компьютере. Сверьте строки со статусом «проверить» и «скан» вручную.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

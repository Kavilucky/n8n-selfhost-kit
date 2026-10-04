#!/usr/bin/env python3
"""Генератор СИНТЕТИЧЕСКИХ актов для проверки парсера: все организации, ИНН, КПП, номера и суммы вымышленные.

ИНН строятся с префиксом 0000 (код налогового органа 0000 не существует) и верной контрольной цифрой: реальной организации с таким номером быть не может.
Запуск: python make_sample_acts.py <папка> [--count 50] [--seed 1] [--hard 3]
Пишет PDF с текстовым слоем (3 шаблона вёрстки + «сложные» формулировки для модели), один PDF-скан без текста (должен получить статус «скан»),
по одному акту с опечаткой в ИНН и с несходящейся суммой, а также _truth.json с эталонными значениями.
Нужен шрифт с кириллицей (Arial, Segoe UI, DejaVu или Liberation: ищется автоматически) и пакет PyMuPDF.
"""
import argparse
import json
import random
import sys
from pathlib import Path

FONTS = ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
NAMES_A = ["Пример-Сервис", "Тест-Логистик", "Образец-Строй", "Вымысел-Консалт", "Макет-Софт", "Условный-Монтаж"]
NAMES_B = ["Демо-Торг", "Пробная-Компания", "Синтетик-Групп", "Эталон-Партнёр", "Фиктив-Проект", "Учебный-Дом"]


def inn10(rng):
    d = [0, 0, 0, 0] + [rng.randint(0, 9) for _ in range(5)]
    w = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    d.append(sum(a * b for a, b in zip(w, d)) % 11 % 10)
    return "".join(map(str, d))


def kpp(rng):
    return "0000" + rng.choice(["01", "43", "02"]) + f"{rng.randint(1, 999):03d}"


def money(x):
    s = f"{x:,.2f}".replace(",", " ").replace(".", ",")
    return s


def find_font():
    for p in FONTS:
        if Path(p).exists():
            return p
    sys.exit("Не найден шрифт с кириллицей (Arial, Segoe UI, DejaVu, Liberation). Укажите путь через переменную FONT_PATH.")


def build_lines(kind, d):
    """Строки текста акта по шаблону."""
    n, dt, ex, cu = d["number"], d["date_ru"], d["exec"], d["cust"]
    net, vat, total = d["net"], d["vat"], d["total"]
    if kind == 1:
        return [f"АКТ № {n} от {dt} г.", "об оказании услуг", "", f"Исполнитель: {ex['name']}, ИНН {ex['inn']}, КПП {ex['kpp']}",
                f"Заказчик: {cu['name']}, ИНН {cu['inn']}, КПП {cu['kpp']}", "", "№ п/п   Наименование услуги            Кол-во   Цена        Сумма",
                f"1       Консультационные услуги       1        {money(net)}   {money(net)}", "",
                f"Сумма без НДС: {money(net)}", f"НДС 20%: {money(vat)}", f"Итого: {money(total)}", "",
                "Услуги оказаны полностью и в срок. Заказчик претензий по объёму, качеству и срокам не имеет."]
    if kind == 2:
        return [f"Акт выполненных работ № {n}", f"Дата: {d['date_num']}", "",
                f"Исполнитель: {ex['name']}", f"ИНН/КПП: {ex['inn']}/{ex['kpp']}", f"Заказчик: {cu['name']}", f"ИНН/КПП: {cu['inn']}/{cu['kpp']}", "",
                "Наименование работ: монтаж и настройка оборудования", f"Стоимость без НДС {money(net)} руб.", f"НДС (20%) {money(vat)} руб.",
                f"Всего к оплате: {money(total)} руб."]
    if kind == 3:
        return [f"АКТ № {n}", f"сдачи-приёмки работ от {dt}", "", f"Исполнитель {ex['name']}", f"ИНН {ex['inn']} КПП {ex['kpp']}",
                f"Заказчик {cu['name']}", f"ИНН {cu['inn']} КПП {cu['kpp']}", "", "Работы выполнены в полном объёме.",
                f"Итого без НДС {money(net)}", f"НДС не облагается", f"Итого с НДС {money(net)}"] if d.get("novat") else [
                f"АКТ № {n}", f"сдачи-приёмки работ от {dt}", "", f"Исполнитель {ex['name']}", f"ИНН {ex['inn']} КПП {ex['kpp']}",
                f"Заказчик {cu['name']}", f"ИНН {cu['inn']} КПП {cu['kpp']}", "", "Работы выполнены в полном объёме.",
                f"Итого без НДС {money(net)}", f"НДС 20% {money(vat)}", f"Итого с НДС {money(total)}"]
    # kind 4: «сложная» формулировка: суммы только в одной фразе, правила их не найдут, нужна модель
    return [f"Акт оказания услуг № {n} ({dt})", "", f"Исполнитель — {ex['name']} (ИНН {ex['inn']}, КПП {ex['kpp']}).",
            f"Заказчик — {cu['name']} (ИНН {cu['inn']}, КПП {cu['kpp']}).", "",
            f"Всего оказано услуг на сумму {money(total)} руб., в том числе НДС (20%) {money(vat)} руб."]


def make_pdf(path, lines, fontfile):
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_font(fontname="F0", fontfile=fontfile)
    y = 70
    for ln in lines:
        page.insert_text((56, y), ln, fontname="F0", fontsize=11)
        y += 18
    try:
        doc.subset_fonts()   # в файл попадают только использованные буквы шрифта (≈50 КБ вместо ≈1 МБ)
    except Exception:
        pass
    doc.save(path, garbage=4, deflate=True)
    doc.close()


def make_scan_pdf(path, lines, fontfile):
    """PDF из одной картинки (как скан): текстового слоя нет."""
    import pymupdf
    tmp = pymupdf.open()
    pg = tmp.new_page()
    pg.insert_font(fontname="F0", fontfile=fontfile)
    y = 70
    for ln in lines:
        pg.insert_text((56, y), ln, fontname="F0", fontsize=11)
        y += 18
    pix = pg.get_pixmap(dpi=110)
    out = pymupdf.open()
    p2 = out.new_page()
    p2.insert_image(p2.rect, pixmap=pix)
    out.save(path)
    out.close(); tmp.close()


def make_acts(folder, count=50, seed=1, hard=3):
    import os
    fontfile = os.environ.get("FONT_PATH") or find_font()
    rng = random.Random(seed)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    truth = {}
    for i in range(1, count + 1):
        net = round(rng.uniform(15000, 480000), 2)
        novat = rng.random() < 0.12
        vat = 0.0 if novat else round(net * 0.2, 2)
        total = round(net + vat, 2)
        month, day, year = rng.randint(1, 12), rng.randint(1, 28), 2026
        ex = {"name": f"ООО «{rng.choice(NAMES_A)}»", "inn": inn10(rng), "kpp": kpp(rng)}
        cu = {"name": f"ООО «{rng.choice(NAMES_B)}»", "inn": inn10(rng), "kpp": kpp(rng)}
        d = {"number": f"{rng.randint(1, 400)}/{year % 100}" if i % 2 else f"{rng.randint(1, 900)}", "date_ru": f"{day} {MONTHS[month - 1]} {year}",
             "date_num": f"{day:02d}.{month:02d}.{year}", "exec": ex, "cust": cu, "net": net, "vat": vat, "total": total, "novat": novat}
        kind = 4 if i > count - hard else (1, 2, 3)[i % 3]
        if kind == 4 and novat:
            d["vat"] = vat = round(net * 0.2, 2); d["total"] = total = round(net + vat, 2); novat = False
        name = f"акт_{i:03d}.pdf"
        expect = {"act_number": d["number"], "act_date": f"{year}-{month:02d}-{day:02d}", "exec_inn": ex["inn"], "exec_kpp": ex["kpp"], "cust_inn": cu["inn"],
                  "cust_kpp": cu["kpp"], "net": net, "vat": vat, "total": total, "kind": kind, "case": "ok"}
        lines = build_lines(kind if not (kind == 3 and novat) else 3, d)
        if i == 7:   # опечатка в ИНН заказчика: проверка должна поймать
            bad = list(cu["inn"]); bad[-1] = str((int(bad[-1]) + 1) % 10); cu_bad = dict(cu, inn="".join(bad))
            d2 = dict(d, cust=cu_bad); lines = build_lines(kind, d2); expect["case"] = "inn_typo"; expect["cust_inn_in_text"] = cu_bad["inn"]
        if i == 11:  # итог не сходится с суммой без НДС и НДС
            d2 = dict(d, total=round(total + 100, 2)); lines = build_lines(kind, d2); expect["case"] = "sum_mismatch"
        if i == 13:  # скан без текстового слоя
            make_scan_pdf(folder / name, lines, fontfile); expect["case"] = "scan"; truth[name] = expect; continue
        make_pdf(folder / name, lines, fontfile)
        truth[name] = expect
    (folder / "_truth.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
    return truth


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--hard", type=int, default=3, help="сколько последних актов с формулировкой, которую правила не разберут (нужна модель)")
    a = ap.parse_args()
    t = make_acts(a.folder, a.count, a.seed, a.hard)
    print(f"Создано {len(t)} вымышленных актов в {a.folder} (эталон: _truth.json). Все данные синтетические.")

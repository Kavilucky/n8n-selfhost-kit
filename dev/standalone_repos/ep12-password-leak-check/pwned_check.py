#!/usr/bin/env python3
"""Проверка пароля на утечку без отправки самого пароля (Pwned Passwords, k-анонимность).

Как это работает:
  1) пароль вводится скрытно (getpass) и не печатается, не пишется в файлы и логи;
  2) SHA-1 от пароля считается на вашем компьютере;
  3) на сервис уходят ТОЛЬКО первые 5 символов хеша: GET https://api.pwnedpasswords.com/range/<5 символов>;
  4) сервис возвращает окончания всех известных хешей с таким началом (тысячи строк, среди них заполняющие записи с числом 0);
  5) ваше окончание ищется в списке на вашем компьютере.

Запуск:
  python pwned_check.py                      проверить один пароль (ввод скрытый)
  python pwned_check.py --file пароли.txt    проверить список (по одному паролю в строке; после проверки удалите файл)
Код возврата: 0 не найден, 1 найден, 2 ошибка.

Честно: «не найден» не значит «надёжный» (база содержит только известные утечки); 5 символов хеша это не абсолютная анонимность;
скрипт зависит от внешнего сервиса и его условий (проверяйте актуальные условия на haveibeenpwned.com/API/v3).
Только стандартная библиотека Python 3.
"""
import argparse
import getpass
import hashlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "https://api.pwnedpasswords.com/range/"
USER_AGENT = "pwned-check-k-anonymity-script/1.0"
HEX5 = re.compile(r"^[0-9A-F]{5}$")
LINE = re.compile(r"^([0-9A-F]{35}):(\d+)$")


def sha1_parts(password):
    """Вернёт (префикс из 5 символов, окончание из 35 символов) SHA-1 в верхнем регистре. Полный хеш наружу не выводится."""
    h = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    return h[:5], h[5:]


def check_base_url(url):
    """Только HTTPS. Исключение для проверки на своём компьютере: http://127.0.0.1 или http://localhost (заглушка в тестах)."""
    u = urllib.parse.urlparse(url)
    if u.scheme == "https":
        return
    if u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1"):
        return
    raise ValueError("Адрес сервиса должен начинаться с https:// (http допустим только для localhost).")


def fetch_range(prefix, base_url=DEFAULT_URL, timeout=20):
    """Запрос диапазона: отправляется только префикс из 5 символов; заголовок Add-Padding: true просит дополнить ответ лишними записями."""
    if not HEX5.match(prefix):
        raise ValueError("префикс должен состоять из 5 шестнадцатеричных символов")
    check_base_url(base_url)
    req = urllib.request.Request(base_url + prefix, headers={"Add-Padding": "true", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_range(body):
    """Разбор ответа: словарь {окончание: число}. Заполняющие записи (число 0) и строки неверного формата отбрасываются."""
    found = {}
    for raw in body.splitlines():
        m = LINE.match(raw.strip().upper())
        if not m:
            continue
        count = int(m.group(2))
        if count > 0:
            found[m.group(1)] = count
    return found


def check_password(password, base_url=DEFAULT_URL, cache=None):
    """Вернёт число появлений пароля в утечках (0 если не найден). cache: словарь префикс -> разобранный ответ."""
    prefix, suffix = sha1_parts(password)
    if cache is not None and prefix in cache:
        table = cache[prefix]
    else:
        table = parse_range(fetch_range(prefix, base_url))
        if cache is not None:
            cache[prefix] = table
    return prefix, table.get(suffix, 0)


def report(count, prefix):
    print(f"На сервис отправлены только первые 5 символов хеша: {prefix}")
    if count:
        print(f"НАЙДЕН: пароль встречается в известных утечках {count} раз(а).")
        print("Смените его везде, где он использовался, и больше им не пользуйтесь.")
    else:
        print("НЕ НАЙДЕН в этой базе. Это не гарантия, что пароль надёжный: проверяйте длину, уникальность и пользуйтесь менеджером паролей.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Проверка пароля на утечку через Pwned Passwords (k-анонимность, только 5 символов хеша уходит наружу).")
    ap.add_argument("--file", help="файл со списком паролей (по одному в строке)")
    ap.add_argument("--base-url", default=DEFAULT_URL, help="адрес диапазона (по умолчанию официальный; http допустим только для localhost)")
    ap.add_argument("--password-stdin", action="store_true", help="прочитать один пароль из стандартного ввода (для автоматизации; небезопаснее скрытого ввода)")
    a = ap.parse_args(argv)
    try:
        check_base_url(a.base_url)
        if a.file:
            cache, found_any, n = {}, False, 0
            with open(a.file, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    pw = line.rstrip("\r\n")
                    if not pw:
                        continue
                    n += 1
                    prefix, cnt = check_password(pw, a.base_url, cache)
                    found_any |= bool(cnt)
                    print(f"строка {i}: " + (f"НАЙДЕН ({cnt} раз)" if cnt else "не найден"))
                    time.sleep(0.05)
            print(f"Проверено паролей: {n}. Пароли не выводились и не сохранялись. После проверки удалите файл со списком.")
            return 1 if found_any else 0
        if a.password_stdin:
            pw = sys.stdin.readline().rstrip("\r\n")
        else:
            pw = getpass.getpass("Пароль (ввод скрыт, на сервис он не отправляется): ")
        if not pw:
            print("Пустой пароль: нечего проверять.")
            return 2
        prefix, cnt = check_password(pw, a.base_url)
        report(cnt, prefix)
        return 1 if cnt else 0
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        print(f"Ошибка: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())

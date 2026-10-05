# check_proxy_ip.py: проверка внешнего IP-адреса домашней сети на сигналы «сдачи в аренду» (резидентный прокси) и плохой репутации.
# Что делает: (1) узнаёт внешний IPv4 (или берёт --ip), (2) проверяет его в открытых DNSBL (Spamhaus ZEN, SpamCop, DroneBL; опционально AbuseIPDB со своим ключом),
# (3) смотрит ТОЛЬКО этот компьютер: слушает ли он порты, типичные для прокси (1080, 3128, 8080, 9050 и т. п.), и отвечает ли порт как SOCKS5.
# Чего НЕ делает: не сканирует чужие адреса, не пробует «взломать» роутер, ничего не отключает и не удаляет, не отправляет файлы и пароли.
# Что уходит наружу: внешний IP в DNS-запросах (его видят ваш DNS-резолвер и оператор списка), запрос к api.ipify.org (если не задан --ip),
# запрос к AbuseIPDB (только если вы сами задали ключ ABUSEIPDB_API_KEY). Только стандартная библиотека Python 3.9+, установка пакетов не нужна.
# Важно: отсутствие IP в списках НЕ доказывает, что сеть чистая: резидентные прокси такие списки часто обходят; запись в PBL Spamhaus для домашнего IP нормальна.
import argparse
import ipaddress
import json
import os
import socket
import sys
import threading
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Зоны DNSBL. Бывший CBL (cbl.abuseat.org) с 2021 года отдаётся из XBL, поэтому отдельно не опрашивается.
ZONES = [
    ("zen.spamhaus.org", "Spamhaus ZEN (SBL, XBL с бывшим CBL, DROP, PBL)"),
    ("bl.spamcop.net", "SpamCop"),
    ("dnsbl.dronebl.org", "DroneBL"),
]
# Типичные порты прокси-серверов (проверяются только на этом компьютере).
PORTS = {1080: "SOCKS", 1081: "SOCKS", 3128: "HTTP-прокси (Squid)", 3129: "HTTP-прокси", 8080: "HTTP-прокси / веб", 8118: "Privoxy", 8888: "HTTP-прокси / веб", 9050: "Tor SOCKS", 9150: "Tor Browser"}

W_LISTED, W_SOCKS_LAN, W_PORT_LAN, W_ABUSE = 50, 30, 15, 40  # вес сигналов в оценке (прозрачная эвристика, не стандарт)
ABUSE_THRESHOLD = 25


def reverse_name(ip, zone):
    """1.2.3.4 + zone -> 4.3.2.1.zone"""
    return ".".join(reversed(ip.split("."))) + "." + zone


def validate_ip(text):
    """Возвращает строку IPv4 или бросает ValueError: DNSBL имеют смысл только для публичного IPv4."""
    ip = ipaddress.ip_address(text.strip())
    if ip.version != 4:
        raise ValueError("поддерживается только IPv4")
    if not ip.is_global:
        raise ValueError("адрес не публичный (локальный, частный или служебный): проверять в DNSBL нечего")
    return str(ip)


def dns_lookup(name, timeout=18.0):
    """Список IPv4-ответов; [] если имени нет (для DNSBL это «не в списке»); None если резолвер не ответил."""
    box = {}

    def run():
        try:
            box["r"] = sorted({a[4][0] for a in socket.getaddrinfo(name, None, socket.AF_INET)})
        except socket.gaierror as e:
            # Windows: 11001 (нет такого хоста), 11004 (нет данных); Linux/macOS: EAI_NONAME, EAI_NODATA
            box["r"] = [] if e.errno in (11001, 11004, getattr(socket, "EAI_NONAME", -2), getattr(socket, "EAI_NODATA", -5)) else None
        except Exception:
            box["r"] = None

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    return box.get("r")


def classify(zone, answers):
    """Ответы DNSBL -> список (метка, тип): hard (серьёзный сигнал), info (справочно), error (источник не дал данных)."""
    out = []
    for a in answers:
        if a.startswith("127.255.255."):
            out.append(("служебный ответ %s: запрос отклонён (публичный резолвер или лимит)" % a, "error"))
        elif zone == "zen.spamhaus.org":
            last = a.split(".")[-1]
            if last in ("2", "3"):
                out.append(("SBL: адрес в списке источников спама (%s)" % a, "hard"))
            elif last in ("4", "5", "6", "7"):
                out.append(("XBL (включая бывший CBL): взломанный или заражённый хост (%s)" % a, "hard"))
            elif last == "9":
                out.append(("DROP: подсеть захвачена злоумышленниками (%s)" % a, "hard"))
            elif last in ("10", "11"):
                out.append(("PBL: адрес из домашнего/динамического диапазона; для обычного домашнего IP это норма (%s)" % a, "info"))
            else:
                out.append(("прочий код Spamhaus %s" % a, "hard"))
        else:
            out.append(("в списке, код %s" % a, "hard"))
    return out


def check_zone(ip, zone, label, lookup=dns_lookup):
    """Проверка одной зоны. Сначала контрольный запрос (127.0.0.2 должен быть «в списке»), иначе резолвер не годится."""
    ctrl = lookup(reverse_name("127.0.0.2", zone))
    if not ctrl or any(a.startswith("127.255.255.") for a in ctrl) or not any(a.startswith("127.0.") for a in ctrl):
        return {"zone": zone, "name": label, "status": "unknown", "details": ["контрольный запрос не прошёл: ваш DNS-резолвер не отвечает как для DNSBL, результат не определён"]}
    ans = lookup(reverse_name(ip, zone))
    if ans is None:
        return {"zone": zone, "name": label, "status": "unknown", "details": ["нет ответа DNS (таймаут или сбой)"]}
    if not ans:
        return {"zone": zone, "name": label, "status": "clean", "details": []}
    cl = classify(zone, ans)
    if any(k == "error" for _, k in cl):
        return {"zone": zone, "name": label, "status": "unknown", "details": [m for m, _ in cl]}
    hard = any(k == "hard" for _, k in cl)
    return {"zone": zone, "name": label, "status": "listed" if hard else "info", "details": [m for m, _ in cl]}


def lan_address():
    """Локальный адрес в сети (без отправки пакетов: connect у UDP-сокета ничего не шлёт)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()


def probe_port(host, port, timeout=0.4):
    """None если закрыт; иначе {'socks5': bool}. SOCKS5-приветствие шлётся только на открытый порт этого компьютера."""
    try:
        c = socket.create_connection((host, port), timeout)
    except OSError:
        return None
    try:
        c.settimeout(timeout)
        socks5 = False
        try:
            c.sendall(b"\x05\x01\x00")
            socks5 = c.recv(2)[:1] == b"\x05"
        except OSError:
            pass
        return {"socks5": socks5}
    finally:
        c.close()


def scan_local(ports=None, lan=None):
    """Порты прокси на ЭТОМ компьютере: на 127.0.0.1 (только локально) и на сетевом адресе (доступно из вашей сети)."""
    ports = PORTS if ports is None else ports
    lan = lan_address() if lan is None else lan
    res = []
    for port, label in sorted(ports.items()):
        for scope, host in (("loopback", "127.0.0.1"), ("lan", lan)):
            if not host or (scope == "lan" and host == "127.0.0.1"):
                continue
            r = probe_port(host, port)
            if r is not None:
                res.append({"port": port, "label": label, "scope": scope, "host": host, "socks5": r["socks5"]})
    return res


def abuseipdb(ip, key, timeout=8.0):
    """Опционально, со СВОИМ ключом (бесплатный план: 1000 проверок в сутки). Возвращает abuseConfidenceScore или None."""
    req = urllib.request.Request("https://api.abuseipdb.com/api/v2/check?ipAddress=%s&maxAgeInDays=90" % ip, headers={"Key": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(json.loads(r.read().decode("utf-8"))["data"]["abuseConfidenceScore"])
    except Exception:
        return None


def detect_public_ip(timeout=6.0):
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as r:
            return validate_ip(r.read().decode("ascii").strip())
    except Exception:
        return None


def score_signals(zones, ports, abuse=None):
    """Оценка 0-100 как сумма весов сигналов. Это эвристика автора, а не вероятность: порог и веса см. константы W_*."""
    s = 0
    reasons = []
    for z in zones:
        if z["status"] == "listed":
            s += W_LISTED
            reasons.append("в списке %s" % z["name"])
    for p in ports:
        if p["scope"] == "lan":
            if p["socks5"]:
                s += W_SOCKS_LAN
                reasons.append("порт %d отвечает как SOCKS5 и открыт для вашей сети" % p["port"])
            else:
                s += W_PORT_LAN
                reasons.append("порт %d (%s) открыт для вашей сети" % (p["port"], p["label"]))
    if abuse is not None and abuse >= ABUSE_THRESHOLD:
        s += W_ABUSE
        reasons.append("AbuseIPDB: оценка жалоб %d из 100" % abuse)
    return min(100, s), reasons


def verdict(score, unknown):
    if score >= 50:
        return "ВЫСОКИЙ РИСК: найдены серьёзные сигналы"
    if score > 0:
        return "ЕСТЬ СИГНАЛЫ: проверьте пункты ниже"
    if unknown:
        return "СИГНАЛОВ НЕ НАЙДЕНО, но проверка неполная: часть источников не ответила"
    return "СИГНАЛОВ НЕ НАЙДЕНО в проверенных источниках (это не гарантия чистоты: резидентные прокси такие списки часто обходят)"


def run_check(ip, lookup=dns_lookup, ports=None, lan=None, abuse_key=None, do_ports=True, abuse_fn=abuseipdb):
    zones = [None] * len(ZONES)  # зоны опрашиваются параллельно: на Windows ответ «нет в списке» может идти около 11 секунд

    def one(i, z, n):
        zones[i] = check_zone(ip, z, n, lookup)
    ths = [threading.Thread(target=one, args=(i, z, n), daemon=True) for i, (z, n) in enumerate(ZONES)]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    open_ports = scan_local(ports, lan) if do_ports else []
    abuse = abuse_fn(ip, abuse_key) if abuse_key else None
    score, reasons = score_signals(zones, open_ports, abuse)
    unknown = sum(1 for z in zones if z["status"] == "unknown") + (1 if abuse_key and abuse is None else 0)
    return {"ip": ip, "zones": zones, "local_ports": open_ports, "abuseipdb": abuse, "signal_score": score, "reasons": reasons, "unknown_sources": unknown, "verdict": verdict(score, unknown)}


def format_report(r):
    mark = {"clean": "не найден", "listed": "В СПИСКЕ", "info": "справочно", "unknown": "нет данных"}
    L = ["Проверка внешнего IP: %s" % r["ip"], "", "Открытые списки (DNSBL):"]
    for z in r["zones"]:
        L.append("  %-45s %s" % (z["name"], mark[z["status"]]))
        L += ["      " + d for d in z["details"]]
    if r["abuseipdb"] is not None:
        L.append("  %-45s оценка жалоб %d из 100" % ("AbuseIPDB (ваш ключ)", r["abuseipdb"]))
    L += ["", "Порты прокси на этом компьютере:"]
    if not r["local_ports"]:
        L.append("  типичные порты прокси не слушаются")
    for p in r["local_ports"]:
        where = "доступен из вашей сети" if p["scope"] == "lan" else "только на этом компьютере"
        L.append("  порт %d (%s): открыт, %s%s" % (p["port"], p["label"], where, ", отвечает как SOCKS5" if p["socks5"] else ""))
    L += ["", "Число сигналов (эвристика автора, 0-100): %d" % r["signal_score"]]
    L += ["  причина: " + x for x in r["reasons"]]
    L += ["", "Вывод: " + r["verdict"], "",
          "Ограничения: скрипт не видит приложения и устройства, которые встроили чужой прокси-модуль (бесплатные VPN, «заработок на трафике», дешёвые ТВ-приставки);",
          "он только показывает признаки и ничего не отключает. Если сигналы есть: проверьте приложения и приставки в сети, смените пароль роутера, обновите его прошивку."]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Проверка внешнего IP на сигналы резидентного прокси и плохой репутации (DNSBL).")
    ap.add_argument("--ip", help="проверить этот публичный IPv4 (иначе определяется через api.ipify.org)")
    ap.add_argument("--no-ports", action="store_true", help="не смотреть порты этого компьютера")
    ap.add_argument("--json", action="store_true", help="вывод в JSON")
    ap.add_argument("--out", help="сохранить отчёт в файл")
    a = ap.parse_args(argv)
    if a.ip:
        try:
            ip = validate_ip(a.ip)
        except ValueError as e:
            print("Ошибка: %s" % e)
            return 2
    else:
        print("Определяю внешний IP через api.ipify.org (сервис увидит ваш IP; чтобы не обращаться к нему, задайте --ip)...")
        ip = detect_public_ip()
        if not ip:
            print("Не удалось определить внешний IP. Узнайте его сами и запустите: python check_proxy_ip.py --ip ВАШ_АДРЕС")
            return 2
    r = run_check(ip, ports=None, abuse_key=os.environ.get("ABUSEIPDB_API_KEY") or None, do_ports=not a.no_ports)
    text = json.dumps(r, ensure_ascii=False, indent=2) if a.json else format_report(r)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + "\n")
    return 1 if r["signal_score"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())

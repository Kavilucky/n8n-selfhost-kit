#!/usr/bin/env python3
# Минимальный локальный RAG: PDF -> пункты -> поиск BM25 -> ответ модели Ollama с цитатой.
# Только стандартная библиотека + pymupdf. Работает без интернета (модель уже скачана в Ollama).
import json
import math
import re
import time
import urllib.request
from collections import Counter

import pymupdf

OLLAMA = "http://127.0.0.1:11434"
CLAUSE_RE = re.compile(r"(?m)^(\d+\.\d+\.)\s")


STOP = {"какой", "какие", "какая", "каком", "какого", "предусмотрены", "предусмотрен", "договором", "договор", "есть", "что", "как", "для", "при", "или"}


def tokens(text):
    # грубый стемминг: нижний регистр и первые 5 букв слова (для русского хватает для поиска)
    return [w[:5] for w in re.findall(r"[a-zа-яё0-9]+", text.lower().replace("ё", "е")) if len(w) > 2 and w not in STOP]


def load_chunks(pdf_path):
    """Возвращает число страниц и список пунктов: {page, num, text, bbox}.
    Пункт = абзац с номером вида 5.1. Если во всём документе таких номеров нет, пункт = текстовый блок страницы."""
    doc = pymupdf.open(pdf_path)
    chunks = []
    for pno, page in enumerate(doc, 1):
        blocks = [(b[:4], re.sub(r"\s+", " ", b[4]).strip()) for b in page.get_text("blocks") if b[6] == 0]
        parts = CLAUSE_RE.split(page.get_text())
        # split даёт [до, номер, текст, номер, текст, ...]
        for i in range(1, len(parts) - 1, 2):
            body = re.sub(r"\s+", " ", parts[i + 1]).strip()
            num = parts[i]
            bbox = next((list(bb) for bb, t in blocks if t.startswith(num)), None)
            chunks.append({"page": pno, "num": num, "text": f"{num} {body}", "bbox": bbox})
    if not chunks:
        for pno, page in enumerate(doc, 1):
            for b in page.get_text("blocks"):
                t = re.sub(r"\s+", " ", b[4]).strip()
                if b[6] == 0 and len(t) >= 40:
                    chunks.append({"page": pno, "num": "", "text": t, "bbox": list(b[:4])})
    return len(doc), chunks


class Index:
    def __init__(self, chunks, k1=1.5, b=0.75):
        self.chunks = chunks
        self.docs = [Counter(tokens(c["text"])) for c in chunks]
        self.len = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.len) / max(1, len(self.len))
        self.df = Counter(t for d in self.docs for t in d)
        self.k1, self.b = k1, b

    def search(self, query, top=3):
        n = len(self.docs)
        scores = []
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in set(tokens(query)):
                if t in d:
                    idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                    f = d[t]
                    s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            scores.append(s)
        order = sorted(range(n), key=lambda i: -scores[i])[:top]
        return [(self.chunks[i], scores[i]) for i in order if scores[i] > 0]


def ask(model, question, hits, on_token=None):
    """Стрим ответа из Ollama. Возвращает текст и метрики самой Ollama (токены, длительность)."""
    ctx = "\n".join(f"[стр. {c['page']}] {c['text']}" for c, _ in hits)
    prompt = ("Ответь на вопрос только по фрагментам договора ниже. Ссылайся на номер пункта. Отвечай кратко списком. В каждом пункте списка дословно процитируй нужную часть пункта договора в кавычках и укажи его номер. "
              "Если ответа нет во фрагментах, так и скажи.\n\nФрагменты:\n" + ctx + "\n\nВопрос: " + question)
    body = json.dumps({"model": model, "prompt": prompt, "stream": True,
                       "options": {"temperature": 0.1, "num_predict": 260}}).encode()
    req = urllib.request.Request(OLLAMA + "/api/generate", body, {"Content-Type": "application/json"})
    out, stats, t0, first = [], {}, time.time(), None
    with urllib.request.urlopen(req) as r:
        for line in r:
            d = json.loads(line)
            if d.get("response"):
                if first is None:
                    first = time.time() - t0
                out.append(d["response"])
                if on_token:
                    on_token(d["response"])
            if d.get("done"):
                stats = d
    return "".join(out), {"first_token_s": first, "wall_s": time.time() - t0, "eval_count": stats.get("eval_count"),
                          "eval_duration_s": stats.get("eval_duration", 0) / 1e9,
                          "prompt_eval_count": stats.get("prompt_eval_count"),
                          "prompt_eval_duration_s": stats.get("prompt_eval_duration", 0) / 1e9,
                          "load_duration_s": stats.get("load_duration", 0) / 1e9}

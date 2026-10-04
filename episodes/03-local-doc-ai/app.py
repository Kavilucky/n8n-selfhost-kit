#!/usr/bin/env python3
# Локальный веб-интерфейс: перетащите PDF, задайте вопрос. Всё работает на вашем компьютере.
# Запуск: start_local_ai.bat (или: python app.py). Адрес: http://localhost:8000
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rag_core as rc

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("LOCAL_AI_PORT", "8000"))
MODEL = os.environ.get("LOCAL_AI_MODEL", "qwen2.5:3b")
MAX_UPLOAD = 60 * 1024 * 1024
STATE = {"pdf": None, "index": None, "name": "", "pages": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if u.path == "/status":
            return self._send(200, {"model": MODEL, "doc": STATE["name"], "pages": STATE["pages"]})
        if u.path == "/page" and STATE["pdf"]:
            n = int(urllib.parse.parse_qs(u.query).get("n", ["1"])[0])
            doc = pymupdf.open(STATE["pdf"])
            n = max(1, min(n, len(doc)))
            pix = doc[n - 1].get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False)
            w, h = doc[n - 1].rect.width, doc[n - 1].rect.height
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("X-Page-Size", f"{w:.1f},{h:.1f}")
            self.send_header("Access-Control-Expose-Headers", "X-Page-Size")
            data = pix.tobytes("png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length", "0"))
        if u.path == "/upload":
            if n <= 0 or n > MAX_UPLOAD:
                return self._send(400, {"error": "файл пустой или больше 60 МБ"})
            data = self.rfile.read(n)
            if not data.startswith(b"%PDF"):
                return self._send(400, {"error": "нужен файл PDF"})
            name = urllib.parse.unquote(self.headers.get("X-Filename", "document.pdf"))
            path = os.path.join(tempfile.gettempdir(), "local_ai_doc.pdf")
            with open(path, "wb") as f:
                f.write(data)
            t = time.time()
            try:
                pages, chunks = rc.load_chunks(path)
            except Exception as e:
                return self._send(400, {"error": f"не удалось прочитать PDF: {e}"})
            if not chunks:
                return self._send(400, {"error": "в PDF нет текста (похоже, скан). Нужен PDF с текстовым слоем."})
            STATE.update(pdf=path, index=rc.Index(chunks), name=name, pages=pages)
            return self._send(200, {"name": name, "pages": pages, "chunks": len(chunks), "seconds": round(time.time() - t, 3)})
        if u.path == "/ask":
            if not STATE["index"]:
                return self._send(400, {"error": "сначала загрузите PDF"})
            try:
                q = json.loads(self.rfile.read(n).decode("utf-8") or "{}").get("question", "").strip()
            except (ValueError, AttributeError):
                return self._send(400, {"error": "некорректный запрос"})
            if not q:
                return self._send(400, {"error": "пустой вопрос"})
            hits = STATE["index"].search(q, top=4)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Connection", "close")
            self.end_headers()

            def emit(obj):
                self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
            try:
                emit({"sources": [{"page": c["page"], "num": c["num"], "bbox": c["bbox"]} for c, _ in hits]})
                if not hits:
                    emit({"token": "В документе не нашлось подходящих фрагментов."})
                else:
                    _, st = rc.ask(MODEL, q, hits, on_token=lambda t: emit({"token": t}))
                    emit({"done": True, "stats": st})
            except Exception as e:
                emit({"error": f"Ollama недоступна или модель не скачана: {e}"})
            return
        self._send(404, {"error": "not found"})


if __name__ == "__main__":
    print(f"Локальный ассистент: http://localhost:{PORT}  (модель {MODEL}). Остановить: Ctrl+C")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()

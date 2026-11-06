"""Disposable PDF text worker. Input/output stay in pipes, never files or logs."""
from __future__ import annotations

import io
import json
import logging
import sys

PDF_LIMIT = 2 * 1024 * 1024
TEXT_LIMIT = 100 * 1024
PAGE_LIMIT = 20


def read_pdf(data: bytes) -> dict:
    from pypdf import PdfReader

    if len(data) > PDF_LIMIT:
        return {"error": "size"}
    if b"%PDF-" not in data[:1024]:
        return {"error": "invalid"}
    reader = PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted:
        return {"error": "encrypted"}
    if len(reader.pages) > PAGE_LIMIT:
        return {"error": "pages"}
    parts = []
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        total += len(text.encode("utf-8")) + 1
        if total > TEXT_LIMIT:
            return {"error": "text_size"}
        parts.append(text)
    text = "\n".join(parts).strip()
    return {"text": text} if text else {"error": "no_text"}


def limit_resources():
    import resource

    limits = [(resource.RLIMIT_CPU, 5), (resource.RLIMIT_CORE, 0), (resource.RLIMIT_FSIZE, 0)]
    if sys.platform.startswith("linux"):
        limits.append((resource.RLIMIT_AS, 256 * 1024 * 1024))
    for kind, value in limits:
        _, hard = resource.getrlimit(kind)
        maximum = value if hard == resource.RLIM_INFINITY else min(value, hard)
        resource.setrlimit(kind, (maximum, maximum))


def main():
    logging.disable(logging.CRITICAL)
    try:
        limit_resources()
        result = read_pdf(sys.stdin.buffer.read(PDF_LIMIT + 1))
    except ImportError:
        result = {"error": "unavailable"}
    except Exception:
        result = {"error": "invalid"}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()

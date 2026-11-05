"""Извлечение текста из материалов — ТОЛЬКО в память, на диск не пишет (ТЗ §13).

md/txt — как есть; docx — python-docx; xlsx — openpyxl; pdf — текстовый слой.
Маркеры привязки: страница (pdf) / лист+строка (xlsx) / абзац (docx) / строка (md, txt).
Статусы: «извлечено» / «не извлекается» (повреждён, зашифрован, скан без
текстового слоя, пустой результат) — явные, не молча.

Важно: CLI выводит только СТАТУС (JSON без текста) — немаскированный текст
не должен попадать в stdout/диалог. Сам текст доступен только как возвращаемое
значение при импорте модуля (в памяти процесса-сканера).

СТАТУС РЕАЛИЗАЦИИ: этап 0.2 — реализовано; тестируется тестами 1–2 (tests/README.md).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SUPPORTED = {".md", ".txt", ".docx", ".xlsx", ".pdf"}


def _fail(reason: str) -> dict:
    return {"status": "not_extractable", "reason": reason}


def _read_plain(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("не удалось декодировать файл")


def _extract_docx(path: Path) -> dict:
    try:
        import docx  # python-docx
    except ImportError:
        return _fail("библиотека python-docx не установлена")
    document = docx.Document(str(path))
    parts: list[str] = []
    for i, para in enumerate(document.paragraphs, 1):
        t = para.text.strip()
        if t:
            parts.append(f"[абзац {i}] {t}")
    for ti, table in enumerate(document.tables, 1):
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(f"[таблица {ti}] " + " | ".join(cells))
    text = "\n".join(parts)
    if not text.strip():
        return _fail("пустой результат")
    return {"status": "ok", "text": text, "anchor_type": "para"}


def _extract_xlsx(path: Path) -> dict:
    try:
        import openpyxl
    except ImportError:
        return _fail("библиотека openpyxl не установлена")
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    parts: list[str] = []
    try:
        for ws in wb.worksheets:
            for n, row in enumerate(ws.iter_rows(values_only=True), 1):
                cells = ["" if v is None else str(v).strip() for v in row]
                if any(cells):
                    parts.append(f"[лист «{ws.title}», строка {n}] " + " | ".join(cells))
    finally:
        wb.close()
    text = "\n".join(parts)
    if not text.strip():
        return _fail("пустой результат")
    return {"status": "ok", "text": text, "anchor_type": "sheet_row"}


def _extract_pdf(path: Path) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError:
        return _fail("библиотека pypdf не установлена")
    reader = PdfReader(str(path))
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            return _fail("зашифрован")
    parts: list[str] = []
    for i, page in enumerate(reader.pages, 1):
        t = (page.extract_text() or "").strip()
        if t:
            parts.append(f"[страница {i}]\n{t}")
    text = "\n".join(parts)
    if not text.strip():
        # пустой текстовый слой = скан без распознанного текста:
        # честный статус «не проверено на секреты», а не «находок нет»
        return _fail("пустой результат (возможно, скан без текстового слоя)")
    return {"status": "ok", "text": text, "anchor_type": "page"}


def extract(path: str) -> dict:
    """Извлечь текст с маркерами привязки.

    Возвращает {"status": "ok", "text": ..., "anchor_type": ...}
    или {"status": "not_extractable", "reason": ...}.
    Текст живёт только в памяти; на диск функция ничего не пишет.
    """
    p = Path(path)
    if not p.is_file():
        return _fail("файл не найден")
    suffix = p.suffix.lower()
    if suffix not in SUPPORTED:
        return _fail("формат не поддерживается: " + (suffix or "без расширения"))
    if p.stat().st_size == 0:
        return _fail("пустой файл")
    try:
        if suffix in {".md", ".txt"}:
            text = _read_plain(p)
            if not text.strip():
                return _fail("пустой результат")
            return {"status": "ok", "text": text, "anchor_type": "line"}
        if suffix == ".docx":
            return _extract_docx(p)
        if suffix == ".xlsx":
            return _extract_xlsx(p)
        return _extract_pdf(p)
    except Exception:
        return _fail("повреждён или не читается")


def main() -> None:
    parser = argparse.ArgumentParser(description="Извлечение текста в память (ТЗ §13)")
    parser.add_argument("path", help="путь к материалу")
    parser.add_argument(
        "--json",
        action="store_true",
        help="вывести статус извлечения в JSON (без текста)",
    )
    args = parser.parse_args()

    result = extract(args.path)
    # CLI никогда не выводит текст — только статус (и причину, если она не читается).
    status: dict = {"status": result["status"]}
    if result["status"] == "ok":
        status["anchor_type"] = result["anchor_type"]
    else:
        status["reason"] = result["reason"]
    print(json.dumps(status, ensure_ascii=False))
    if result["status"] != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()

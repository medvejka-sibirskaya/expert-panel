"""Извлечение текста из материалов — ТОЛЬКО в память, на диск не пишет (ТЗ §13).

md/txt — как есть; docx — python-docx; xlsx — openpyxl; pdf — текстовый слой.
Маркеры привязки: страница (pdf) / лист+строка (xlsx) / абзац (docx) / строка (md, txt).
Статусы: «извлечено» / «не извлекается» (повреждён, зашифрован, скан без
текстового слоя, пустой результат) — явные, не молча.

Важно: CLI выводит только СТАТУС (JSON без текста) — немаскированный текст
не должен попадать в stdout/диалог. Сам текст доступен только как возвращаемое
значение при импорте модуля (в памяти процесса-сканера).

СТАТУС РЕАЛИЗАЦИИ: каркас (этап 0) — интерфейс зафиксирован, логика не реализована.
"""
from __future__ import annotations

import argparse
import json
import sys


def extract(path: str) -> dict:
    """Извлечь текст с маркерами привязки.

    Возвращает {"status": "ok", "text": ..., "anchor_type": ...}
    или {"status": "not_extractable", "reason": ...}.
    Текст живёт только в памяти; на диск функция ничего не пишет.
    """
    raise NotImplementedError("extract_text.extract: этап 0 — логика не реализована")


def main() -> None:
    parser = argparse.ArgumentParser(description="Извлечение текста в память (ТЗ §13)")
    parser.add_argument("path", help="путь к материалу")
    parser.add_argument(
        "--json",
        action="store_true",
        help="вывести статус извлечения в JSON (без текста)",
    )
    args = parser.parse_args()

    # Этап 0: каркас — логика не реализована.
    # Честный статус вместо молчания: это НЕ «извлечено» и НЕ «не извлекается»,
    # а нереализованный этап.
    if args.json:
        print(json.dumps({"status": "not_implemented", "stage": "0"}, ensure_ascii=False))
    sys.exit("extract_text: не реализовано — этап 0 (каркас), см. ТЗ §13 и tests\\README.md")


if __name__ == "__main__":
    main()
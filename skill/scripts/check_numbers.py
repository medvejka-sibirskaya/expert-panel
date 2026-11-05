"""Вычислимые проверки документа: числа, даты, суммы, схемы (ТЗ §13).

Внутренняя непротиворечивость: суммы сходятся, даты в порядке, схемы
(например, нумерация блоков) непрерывны. Только форматы и вычислимое —
семантику проверяет эксперт-аудитор фактов, не скрипт (принцип ТЗ §2.3).

СТАТУС РЕАЛИЗАЦИИ: этап 0.2 — реализовано (MVP-набор: даты, порядок дат,
суммы «a + b = c», нумерация списков).
"""
from __future__ import annotations

import argparse
import calendar
import json
import re
import sys
from pathlib import Path

import scan_secrets  # anchor_for — общий расчёт маркеров привязки

DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
DATE_PAIR_RE = re.compile(
    r"с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)
# число: цифры с необязательными разрядными пробелами (10 000) и дробной частью (2.5)
_NUM = r"(\d+(?: \d{3})*(?:[.,]\d+)?)"
SUM_RE = re.compile(_NUM + r"\s*\+\s*" + _NUM + r"\s*=\s*" + _NUM)
LIST_ITEM_RE = re.compile(r"^\s*(\d+)[.)]\s", re.MULTILINE)


def _valid_date(d: int, m: int, y: int) -> bool:
    if not (1900 <= y <= 2100):
        return False
    if not (1 <= m <= 12):
        return False
    return 1 <= d <= calendar.monthrange(y, m)[1]


def _num(s: str) -> float:
    s = s.replace(" ", "").replace(" ", "")
    s = s.rstrip(".,")
    if "," in s:
        s = s.replace(",", ".")
    return float(s)


def _finding(o_name: str, anchor: str, check: str, result: str) -> dict:
    return {"o_name": o_name, "anchor": anchor, "check": check, "result": result}


def _check_dates(o_name: str, text: str, findings: list[dict]) -> None:
    for m in DATE_RE.finditer(text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not _valid_date(d, mo, y):
            findings.append(_finding(o_name, scan_secrets.anchor_for(text, m.start()),
                                     "date_invalid",
                                     f"недопустимая дата: {m.group(0)}"))
    for m in DATE_PAIR_RE.finditer(text):
        d1 = tuple(int(x) for x in m.group(1).split("."))
        d2 = tuple(int(x) for x in m.group(2).split("."))
        if _valid_date(*d1) and _valid_date(*d2) and d1 > d2:
            findings.append(_finding(o_name, scan_secrets.anchor_for(text, m.start()),
                                     "date_order",
                                     f"конец раньше начала: с {m.group(1)} по {m.group(2)}"))


def _check_sums(o_name: str, text: str, findings: list[dict]) -> None:
    for m in SUM_RE.finditer(text):
        try:
            a, b, c = _num(m.group(1)), _num(m.group(2)), _num(m.group(3))
        except ValueError:
            continue
        if abs(c - (a + b)) > max(0.01, abs(c) * 0.001):
            findings.append(_finding(o_name, scan_secrets.anchor_for(text, m.start()),
                                     "sum_mismatch",
                                     f"сумма не сходится: {m.group(0).strip()}"))


def _check_numbering(o_name: str, text: str, findings: list[dict]) -> None:
    prev: int | None = None
    for m in LIST_ITEM_RE.finditer(text):
        n = int(m.group(1))
        anchor = scan_secrets.anchor_for(text, m.start())
        if prev is not None:
            if n == prev:
                findings.append(_finding(o_name, anchor, "numbering_duplicate",
                                         f"дубль в нумерации: {n}"))
            elif n > prev + 1:
                findings.append(_finding(o_name, anchor, "numbering_gap",
                                         f"пропуск в нумерации: после {prev} идёт {n}"))
        prev = n  # меньший номер = начало новой схемы, счёт продолжается с него


def check(o_name: str, text: str) -> list[dict]:
    """Проверить вычислимое в тексте разрешённой копии.

    Возвращает список находок для координатора: [{"o_name", "anchor",
    "check", "result"}]. Решений не принимает.
    """
    findings: list[dict] = []
    _check_dates(o_name, text, findings)
    _check_sums(o_name, text, findings)
    _check_numbering(o_name, text, findings)
    return findings


def main() -> None:
    parser = argparse.ArgumentParser(description="Вычислимые проверки: числа/даты/схемы (ТЗ §13)")
    parser.add_argument("--o-name", required=True, help="имя материала (O1, O2…)")
    parser.add_argument("path", help="путь к разрешённой копии")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_file():
        print(json.dumps({"status": "error", "reason": "файл не найден"}, ensure_ascii=False))
        sys.exit(1)
    text = path.read_text(encoding="utf-8", errors="replace")
    print(json.dumps({"status": "ok", "o_name": args.o_name,
                      "findings": check(args.o_name, text)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Вычислимые проверки документа: числа, даты, суммы, схемы (ТЗ §13).

Внутренняя непротиворечивость: суммы сходятся, даты в порядке, схемы
(например, нумерация блоков) непрерывны. Только форматы и вычислимое —
семантику проверяет эксперт-аудитор фактов, не скрипт (принцип ТЗ §2.3).

СТАТУС РЕАЛИЗАЦИИ: каркас (этап 0) — интерфейс зафиксирован, логика не реализована.
"""
from __future__ import annotations

import argparse
import sys


def check(o_name: str, text: str) -> list[dict]:
    """Проверить вычислимое в тексте разрешённой копии.

    Возвращает список находок для координатора: [{"o_name", "anchor",
    "check", "result"}]. Решений не принимает.
    """
    raise NotImplementedError("check_numbers.check: этап 0 — логика не реализована")


def main() -> None:
    parser = argparse.ArgumentParser(description="Вычислимые проверки: числа/даты/схемы (ТЗ §13)")
    parser.add_argument("--o-name", required=True, help="имя материала (O1, O2…)")
    parser.add_argument("path", help="путь к разрешённой копии")
    args = parser.parse_args()

    # Этап 0: каркас — логика не реализована.
    sys.exit("check_numbers: не реализовано — этап 0 (каркас), см. ТЗ §13")


if __name__ == "__main__":
    main()
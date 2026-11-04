"""Подбор кандидатов на сопоставление замечаний двух отчётов (ТЗ §12, §13).

Скрипт готовит кандидатов: location + категория + пересечение ключевых слов.
Классификацию (новые / устранённые / повторившиеся / изменившиеся) делает
координатор — скрипт решений не принимает. Метод помечается в отчёте сравнения.

СТАТУС РЕАЛИЗАЦИИ: каркас (этап 0) — интерфейс зафиксирован, логика не реализована.
"""
from __future__ import annotations

import argparse
import sys


def candidates(old: dict, new: dict) -> list[dict]:
    """Вернуть кандидатов на сопоставление замечаний.

    Каждый кандидат: {"old_id", "new_id", "location_match", "category",
    "keyword_overlap"} — данные для решения координатора, не решение.
    """
    raise NotImplementedError("compare_reports.candidates: этап 0 — логика не реализована")


def main() -> None:
    parser = argparse.ArgumentParser(description="Кандидаты сопоставления замечаний (ТЗ §13)")
    parser.add_argument("old", help="JSON предыдущего отчёта")
    parser.add_argument("new", help="JSON нового отчёта")
    args = parser.parse_args()

    # Этап 0: каркас — логика не реализована.
    sys.exit("compare_reports: не реализовано — этап 0 (каркас), см. ТЗ §12, §13")


if __name__ == "__main__":
    main()
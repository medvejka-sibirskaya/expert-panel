"""Сборка отчётов MD + JSON из данных вердикта (ТЗ §9, §13).

Два файла на запуск с общим run_id: <run_id>.md (человекочитаемый) и
<run_id>.json (структурированный, схема ТЗ §9). Перед записью:
- ПОСТ-МАСКА секретов и контактных ПД по всем финальным текстам — эксперт
  мог воспроизвести контакт в замечании, маска обязана его поймать;
- валидация JSON-схемы;
- retention_until по retention_days (по умолчанию 90).
Исходные пути и имена материалов в отчёты не пишутся — только O-имена.

СТАТУС РЕАЛИЗАЦИИ: каркас (этап 0) — интерфейс зафиксирован, логика не реализована.
"""
from __future__ import annotations

import argparse
import sys


def build(verdict_data: dict, out_dir: str) -> tuple[str, str]:
    """Собрать MD и JSON с общим run_id. Возвращает пути обоих файлов.

    verdict_data — словарь по схеме ТЗ §9 (run_id, object, goal, preflight_summary,
    findings, verdict, scores, expert_disagreements, checked_areas,
    unchecked_areas, limitations, recommendations, token_stats,
    accepted_risks, retention_until, schema_version).
    """
    raise NotImplementedError("report.build: этап 0 — логика не реализована")


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборка отчётов MD+JSON (ТЗ §13)")
    parser.add_argument("--input", required=True, help="JSON с данными вердикта (схема ТЗ §9)")
    parser.add_argument("--out-dir", required=True, help="D:\\expert-panel\\reports")
    parser.add_argument("--retention-days", type=int, default=90,
                        help="срок хранения отчёта в днях (по умолчанию 90)")
    args = parser.parse_args()

    # Этап 0: каркас — логика не реализована.
    sys.exit("report: не реализовано — этап 0 (каркас), см. ТЗ §9, §13")


if __name__ == "__main__":
    main()
"""Журнал комиссии: append-only JSONL, lock, проверка целостности (ТЗ §10, §13).

Файл: D:\\expert-panel\\history\\history.jsonl
Идентификаторы: run_id (UUID запуска) + event_id (уникальный) + seq (глобальный).
Гарантии:
- запись — одна полная строка за вызов, с \\n и flush;
- повтор того же event_id — явная ошибка (идемпотентность);
- повреждённый хвост не трогается молча: перенос в history.quarantine
  с заголовком {repair_id, utc_ts, seq, причина} + запись journal_repaired
  с тем же repair_id — ТОЛЬКО по подтверждению; если событие записать
  не удалось, check видит незакрытый перенос и повторяет только запись события;
- ПД и исходные пути в журнал не пишутся — только O-имена;
- lock: run.lock (PID + run_id); живой чужой lock → отказ; lock мёртвого
  процесса → снятие по подтверждению; обнаружение остатков work\\ от
  незавершённых запусков.

СТАТУС РЕАЛИЗАЦИИ: каркас (этап 0) — интерфейс зафиксирован, логика не реализована.
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Журнал JSONL: события, lock, целостность (ТЗ §13)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("lock", help="создать run.lock (PID + run_id); проверка и снятие — параметрами")
    sub.add_parser("unlock", help="снять run.lock (штатная остановка)")
    sub.add_parser("append", help="записать событие: run_id, event_id, тип, данные (без ПД)")
    sub.add_parser("list", help="список событий (run_id, seq, тип)")
    sub.add_parser("read", help="прочитать события запуска по run_id")
    sub.add_parser("check", help="целостность: JSON-строки, seq непрерывен, event_id уникальны, переносы закрыты")
    sub.add_parser("repair", help="перенос повреждённого хвоста в quarantine с repair_id — по подтверждению")
    args = parser.parse_args()

    # Этап 0: каркас — логика не реализована.
    # Реализация: вместе с тестами §15 (lock, journal check, quarantine+repair_id,
    # дубль event_id) — см. tests\\README.md.
    sys.exit(f"journal {args.command}: не реализовано — этап 0 (каркас), см. ТЗ §10, §13")


if __name__ == "__main__":
    main()
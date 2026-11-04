"""Скан секретов и контактных ПД по извлечённому тексту в памяти (ТЗ §11, §13).

Два набора паттернов:
- секреты: Bearer/token=/api_key=/password=, Telegram-токен, вебхуки;
- контактные ПД: телефоны РФ, email, адреса.

Гарантии:
- вывод только O-имя, маркер привязки, тип — ЗНАЧЕНИЯ не попадают ни в stdout,
  ни в stderr, ни в диагностические логи;
- до выбора режима ничего не маскируется и не копируется;
- разрешённые копии формируются ПОСЛЕ выбора режима: извлечение повторно
  в памяти → маскирование секретов по режиму → контактные ПД всегда → запись
  в work\\<run_id>\\.

СТАТУС РЕАЛИЗАЦИИ: каркас (этап 0) — интерфейс зафиксирован, логика не реализована.
"""
from __future__ import annotations

import argparse
import sys


def scan(o_name: str, extracted: dict) -> list[dict]:
    """Просканировать текст (уже извлечённый, в памяти) на секреты и контактные ПД.

    Возвращает список находок: [{"o_name", "anchor", "kind"}] — только тип,
    без значений.
    """
    raise NotImplementedError("scan_secrets.scan: этап 0 — логика не реализована")


def prepare(o_name: str, extracted: dict, secrets_mode: str, work_dir: str) -> str:
    """Сформировать разрешённую копию в work_dir.

    secrets_mode: "mask" | "exclude" (остановка запуска обрабатывает координатор).
    Контактные ПД маскируются всегда, в любом режиме. Маркеры привязки сохраняются.
    Возвращает путь созданной копии (первый дисковый артефакт запуска).
    """
    raise NotImplementedError("scan_secrets.prepare: этап 0 — логика не реализована")


def main() -> None:
    parser = argparse.ArgumentParser(description="Скан секретов/ПД и разрешённые копии (ТЗ §13)")
    sub = parser.add_subparsers(dest="command", required=True)
    scan_p = sub.add_parser("scan", help="скан текста в памяти; вывод: O-имя/маркер/тип, без значений")
    scan_p.add_argument("--o-name", required=True, help="обезличенное имя материала (O1, O2…)")
    prepare_p = sub.add_parser("prepare", help="формирует разрешённую копию ПОСЛЕ выбора режима")
    prepare_p.add_argument("--o-name", required=True)
    prepare_p.add_argument("--mode", choices=["mask", "exclude"], required=True,
                           help="режим только для секретов; контактные ПД маскируются всегда")
    prepare_p.add_argument("--work-dir", required=True, help="work\\<run_id>")
    args = parser.parse_args()

    # Этап 0: каркас — логика не реализована.
    sys.exit(f"scan_secrets {args.command}: не реализовано — этап 0 (каркас), см. ТЗ §13")


if __name__ == "__main__":
    main()
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

СТАТУС РЕАЛИЗАЦИИ: этап 0.2 — реализовано; тестируется тестами 1–6 (tests/README.md).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import extract_text

# (kind, паттерн, группа_со_значением); group=0 — всё совпадение и есть значение.
SECRET_PATTERNS = [
    ("bearer", re.compile(r"\bBearer\s+([A-Za-z0-9\-._~+/]+=*)", re.IGNORECASE), 1),
    ("api_key", re.compile(r"\bapi[_-]?key\s*[:=]\s*([^\s,;]+)", re.IGNORECASE), 1),
    ("token", re.compile(r"\btoken\s*[:=]\s*([^\s,;]+)", re.IGNORECASE), 1),
    ("password", re.compile(r"\b(?:password|pass|пароль)\s*[:=]\s*([^\s,;]+)", re.IGNORECASE), 1),
    ("telegram_token", re.compile(r"\b(\d{8,10}:[A-Za-z0-9_-]{35})\b"), 1),
    ("webhook", re.compile(
        r"\b(https?://\S*(?:webhook|hooks\.slack\.com|api\.telegram\.org/bot)\S*)",
        re.IGNORECASE), 1),
]

PII_PATTERNS = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 0),
    ("phone", re.compile(
        r"(?<!\d)(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)"), 0),
    ("address", re.compile(
        r"\b(?:ул\.?|улица|пр-т\.?|просп\.?|проспект|пер\.?|переулок|ш\.?|шоссе)\s*"
        r"[^,\n]+?,?\s*(?:д\.?|дом)\s*\d+",
        re.IGNORECASE), 0),
]

PII_MASKS = {"email": "[EMAIL]", "phone": "[ТЕЛЕФОН]", "address": "[АДРЕС]"}

_MARKER_RE = re.compile(r"^\[[^\]\n]+\]", re.MULTILINE)


def _replace(pattern: re.Pattern, group: int, replacement: str, text: str) -> str:
    if group == 0:
        return pattern.sub(replacement, text)
    return pattern.sub(lambda m: m.group(0).replace(m.group(1), replacement), text)


def anchor_for(text: str, pos: int, anchor_type: str = "auto") -> str:
    """Человекочитаемый маркер привязки для позиции pos в тексте.

    auto (md/txt и все маркерные форматы): ближайший маркер [ ... ] выше по
    тексту; если маркеров нет — номер строки.
    """
    if anchor_type != "line":
        last = None
        for m in _MARKER_RE.finditer(text[:pos]):
            last = m
        if last is not None:
            return last.group(0)
    return f"строка {text.count(chr(10), 0, pos) + 1}"


def mask_text(text: str, *, secrets_mode: str = "mask", mask_contacts: bool = True) -> str:
    """Маскировать текст: секреты по режиму, контактные ПД — всегда.

    secrets_mode: "mask" — значение секрета заменяется на [СЕКРЕТ:вид];
    "exclude" — строка с секретом заменяется целиком (исключённый участок
    фиксируется как непроверенный). Маркеры привязки сохраняются.
    """
    if secrets_mode == "exclude":
        kept: list[str] = []
        for line in text.split("\n"):
            if any(p.search(line) for _, p, _ in SECRET_PATTERNS):
                kept.append("[УЧАСТОК ИСКЛЮЧЁН — не проверялся]")
            else:
                kept.append(line)
        text = "\n".join(kept)
    elif secrets_mode == "mask":
        for kind, pattern, grp in SECRET_PATTERNS:
            text = _replace(pattern, grp, f"[СЕКРЕТ:{kind}]", text)
    else:
        raise ValueError("неизвестный режим обработки секретов: " + str(secrets_mode))
    if mask_contacts:
        for kind, pattern, grp in PII_PATTERNS:
            text = _replace(pattern, grp, PII_MASKS[kind], text)
    return text


def scan(o_name: str, extracted: dict) -> list[dict]:
    """Просканировать текст (уже извлечённый, в памяти) на секреты и контактные ПД.

    Возвращает список находок: [{"o_name", "anchor", "kind", "category"}] —
    только тип и маркер, без значений и без фрагментов текста.
    """
    if extracted.get("status") != "ok":
        return []
    text = extracted["text"]
    anchor_type = extracted.get("anchor_type", "auto")
    hits: list[tuple] = []
    for category, patterns in (("secret", SECRET_PATTERNS), ("contact_pii", PII_PATTERNS)):
        for kind, pattern, _grp in patterns:
            for m in pattern.finditer(text):
                hits.append((m.start(), anchor_for(text, m.start(), anchor_type), kind, category))
    hits.sort(key=lambda h: h[0])
    return [{"o_name": o_name, "anchor": anchor, "kind": kind, "category": category}
            for _start, anchor, kind, category in hits]


def prepare(o_name: str, extracted: dict, secrets_mode: str, work_dir: str) -> str:
    """Сформировать разрешённую копию в work_dir (первый дисковый артефакт запуска).

    secrets_mode: "mask" | "exclude" (остановка запуска — решение координатора).
    Контактные ПД маскируются всегда, в любом режиме. Маркеры привязки
    сохраняются. Текст маскируется в памяти и только потом пишется на диск.
    """
    if extracted.get("status") != "ok":
        raise ValueError("текст не извлечён — разрешённую копию не сформировать")
    text = mask_text(extracted["text"], secrets_mode=secrets_mode, mask_contacts=True)
    out = Path(work_dir) / f"{o_name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return str(out)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Скан секретов/ПД и разрешённые копии (ТЗ §13)")
    sub = parser.add_subparsers(dest="command", required=True)
    scan_p = sub.add_parser("scan", help="скан текста в памяти; вывод: O-имя/маркер/тип, без значений")
    scan_p.add_argument("--o-name", required=True, help="обезличенное имя материала (O1, O2…)")
    scan_p.add_argument("--path", required=True, help="путь к материалу (текст извлекается в память)")
    prepare_p = sub.add_parser("prepare", help="формирует разрешённую копию ПОСЛЕ выбора режима")
    prepare_p.add_argument("--o-name", required=True)
    prepare_p.add_argument("--path", required=True, help="путь к материалу (извлечение повторно в памяти)")
    prepare_p.add_argument("--mode", choices=["mask", "exclude"], required=True,
                           help="режим только для секретов; контактные ПД маскируются всегда")
    prepare_p.add_argument("--work-dir", required=True, help="work\\<run_id>")
    args = parser.parse_args()

    # Текст живёт в памяти процесса; на диск (и в stdout) идут только статусы
    # и находки без значений.
    extracted = extract_text.extract(args.path)
    if extracted["status"] != "ok":
        _emit({"status": "not_extractable", "o_name": args.o_name,
               "note": "не проверено на секреты", "reason": extracted["reason"]})
        sys.exit(1)

    if args.command == "scan":
        findings = scan(args.o_name, extracted)
        _emit({"status": "ok", "o_name": args.o_name, "findings": findings})
    else:
        copy_path = prepare(args.o_name, extracted, args.mode, args.work_dir)
        _emit({"status": "ok", "o_name": args.o_name, "copy": copy_path})


if __name__ == "__main__":
    main()

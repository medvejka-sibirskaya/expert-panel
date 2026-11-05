"""Подбор кандидатов на сопоставление замечаний двух отчётов (ТЗ §12, §13).

Скрипт готовит кандидатов: location + категория + пересечение ключевых слов.
Классификацию (новые / устранённые / повторившиеся / изменившиеся) делает
координатор — скрипт решений не принимает. Метод помечается в отчёте сравнения.

СТАТУС РЕАЛИЗАЦИИ: этап 0.2 — реализовано.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOKEN_RE = re.compile(r"[а-яёa-z0-9]{4,}")


def _tokens(finding: dict) -> set[str]:
    src = " ".join([str(finding.get("problem", "")), str(finding.get("recommendation", ""))])
    return set(TOKEN_RE.findall(src.lower()))


def candidates(old: dict, new: dict) -> list[dict]:
    """Вернуть кандидатов на сопоставление замечаний.

    Каждый кандидат: {"old_id", "new_id", "location_match", "category",
    "keyword_overlap"} — данные для решения координатора, не решение.
    """
    out: list[dict] = []
    for of in old.get("findings", []) or []:
        for nf in new.get("findings", []) or []:
            location_match = (of.get("location", "") == nf.get("location", "")
                              and bool(of.get("location")))
            cats = []
            if of.get("priority") == nf.get("priority"):
                cats.append("same_priority")
            if of.get("type") == nf.get("type"):
                cats.append("same_type")
            to, tn = _tokens(of), _tokens(nf)
            union = to | tn
            overlap = len(to & tn) / len(union) if union else 0.0
            if not (location_match or cats or overlap >= 0.2):
                continue
            out.append({"old_id": of.get("id"), "new_id": nf.get("id"),
                        "location_match": location_match,
                        "category": ",".join(cats),
                        "keyword_overlap": round(overlap, 2)})
    out.sort(key=lambda c: (c["location_match"], c["keyword_overlap"]), reverse=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Кандидаты сопоставления замечаний (ТЗ §13)")
    parser.add_argument("old", help="JSON предыдущего отчёта")
    parser.add_argument("new", help="JSON нового отчёта")
    args = parser.parse_args()

    try:
        old = json.loads(Path(args.old).read_text(encoding="utf-8"))
        new = json.loads(Path(args.new).read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"status": "error", "reason": "не удалось прочитать JSON: " + str(e)},
                         ensure_ascii=False))
        sys.exit(1)
    print(json.dumps({"status": "ok", "candidates": candidates(old, new)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

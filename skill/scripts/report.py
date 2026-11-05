"""Сборка отчётов MD + JSON из данных вердикта (ТЗ §9, §13).

Два файла на запуск с общим run_id: <run_id>.md (человекочитаемый) и
<run_id>.json (структурированный, схема ТЗ §9). Перед записью:
- ПОСТ-МАСКА секретов и контактных ПД по всем финальным текстам — эксперт
  мог воспроизвести контакт в замечании, маска обязана его поймать;
- валидация JSON-схемы;
- retention_until по retention_days (по умолчанию 90; env
  EXPERT_PANEL_RETENTION_DAYS, пустое значение = дефолт).
Исходные пути и имена материалов в отчёты не пишутся — только O-имена.

СТАТУС РЕАЛИЗАЦИИ: этап 0.2 — реализовано; тестируется тестами 5, 7
(tests/README.md). По ревью Жоры №4 (п. 4.4): _validate проверяет тип
preflight_summary (объект), оба формата отчёта рендерятся в памяти
и записываются только после успешного рендеринга — частичной записи нет.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import scan_secrets

SCHEMA_VERSION = "1"
DEFAULT_RETENTION_DAYS = 90

REQUIRED_TOP = ["run_id", "object", "goal", "preflight_summary", "findings", "verdict",
                "scores", "checked_areas", "unchecked_areas", "limitations",
                "recommendations", "token_stats"]
FINDING_FIELDS = ["id", "priority", "type", "location", "evidence", "problem",
                  "consequence", "recommendation", "confidence"]


class SchemaError(Exception):
    """Входные данные не соответствуют схеме ТЗ §9/§7."""


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _env_default() -> int:
    """retention_days из env; пустое/отсутствующее значение → дефолт 90."""
    raw = os.environ.get("EXPERT_PANEL_RETENTION_DAYS", "")
    if not raw.strip():
        return DEFAULT_RETENTION_DAYS
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_RETENTION_DAYS


def post_mask(obj):
    """Глубоко прогнать пост-маску по всем строкам данных вердикта."""
    if isinstance(obj, str):
        return scan_secrets.mask_text(obj, secrets_mode="mask", mask_contacts=True)
    if isinstance(obj, list):
        return [post_mask(v) for v in obj]
    if isinstance(obj, dict):
        return {k: post_mask(v) for k, v in obj.items()}
    return obj


def _validate(data: dict) -> list[str]:
    problems: list[str] = []
    for field in REQUIRED_TOP:
        if field not in data:
            problems.append("отсутствует поле: " + field)
    obj = data.get("object")
    if isinstance(obj, dict):
        mats = obj.get("materials")
        if not isinstance(mats, list) or any(not isinstance(m, dict) for m in mats):
            problems.append("object.materials должен быть списком объектов")
    else:
        problems.append("object должен быть объектом с type и materials")
    findings = data.get("findings")
    if isinstance(findings, list):
        for i, f in enumerate(findings, 1):
            if not isinstance(f, dict):
                problems.append(f"замечание {i}: не объект")
                continue
            for field in FINDING_FIELDS:
                if field not in f:
                    problems.append(f"замечание {i}: отсутствует поле {field}")
    else:
        problems.append("findings должен быть списком")
    if not isinstance(data.get("preflight_summary"), dict):
        problems.append("preflight_summary должен быть объектом {experts, models, depth}")
    for field in ("checked_areas", "unchecked_areas", "limitations", "recommendations"):
        if field in data and not isinstance(data[field], list):
            problems.append(field + " должен быть списком")
    if not isinstance(data.get("scores"), dict):
        problems.append("scores должен быть объектом критерий → оценка")
    return problems


def _render_finding(f: dict) -> str:
    return "\n".join([
        f"### {f.get('id', '')} — {f.get('priority', '')} ({f.get('type', '')})",
        f"- Расположение: {f.get('location', '')}",
        f"- Цитата: «{f.get('evidence', '')}»",
        f"- Проблема: {f.get('problem', '')}",
        f"- Последствие: {f.get('consequence', '')}",
        f"- Рекомендация: {f.get('recommendation', '')}",
        f"- Уверенность автора: {f.get('confidence', '')}",
    ])


def _render_md(data: dict) -> str:
    L: list[str] = []
    a = L.append
    obj = data["object"]
    mats = ", ".join(str(m.get("o_name", "?")) for m in obj.get("materials", []))
    a("# Отчёт экспертной комиссии")
    a("")
    a(f"- Запуск: `{data['run_id']}`")
    a(f"- Создан (UTC): {data.get('created_utc', '')}")
    a(f"- Объект: {obj.get('type', '')}; материалы: {mats}")
    a(f"- Цель: {data['goal']}")
    a("")
    a("## Вердикт")
    a("")
    a(f"**{data['verdict']}**")
    a("")
    ps = data.get("preflight_summary") or {}
    if ps:
        experts = ", ".join(str(x) for x in ps.get("experts", []))
        models = ", ".join(str(x) for x in ps.get("models", []))
        a(f"- Состав: {experts}")
        a(f"- Модели: {models}")
        a(f"- Глубина: {ps.get('depth', '')}")
        a("")
    a("## Оценка по критериям")
    a("")
    a("| Критерий | Оценка |")
    a("|---|---|")
    for crit, val in (data.get("scores") or {}).items():
        a(f"| {crit} | {val} |")
    a("")
    groups = [("Критичные", "Критично"), ("Важные", "Важно"),
              ("Желательные", "Желательно"), ("Вопросы", "Вопрос")]
    seen: set[int] = set()
    for title, prio in groups:
        fs = [f for f in data.get("findings", []) if f.get("priority") == prio]
        if not fs:
            continue
        a(f"## {title}")
        a("")
        for f in fs:
            seen.add(id(f))
            a(_render_finding(f))
            a("")
    leftovers = [f for f in data.get("findings", []) if id(f) not in seen]
    if leftovers:
        a("## Прочие замечания")
        a("")
        for f in leftovers:
            a(_render_finding(f))
            a("")
    if data.get("expert_disagreements"):
        a("## Разногласия экспертов")
        a("")
        for d in data["expert_disagreements"]:
            a(f"- {d}")
        a("")
    for title, field in (("Проверенные области", "checked_areas"),
                         ("Непроверенные области", "unchecked_areas"),
                         ("Ограничения", "limitations")):
        items = data.get(field) or []
        if items:
            a(f"## {title}")
            a("")
            for item in items:
                a(f"- {item}")
            a("")
    recs = data.get("recommendations") or []
    if recs:
        a("## Рекомендации и порядок исправлений")
        a("")
        for i, r in enumerate(recs, 1):
            a(f"{i}. {r}")
        a("")
    if data.get("token_stats") is not None:
        a("## Статистика токенов (оценка)")
        a("")
        a("```json")
        a(json.dumps(data["token_stats"], ensure_ascii=False))
        a("```")
        a("")
    if data.get("accepted_risks"):
        a("## Принятые пользователем риски")
        a("")
        for r in data["accepted_risks"]:
            a(f"- {r}")
        a("")
    a("## Срок хранения")
    a("")
    a(f"Отчёт хранится до: {data.get('retention_until', '')} (retention_days; "
      "удаление — только по подтверждению).")
    a("")
    return "\n".join(L)


def build(verdict_data: dict, out_dir: str, retention_days: int = DEFAULT_RETENTION_DAYS) -> tuple[str, str]:
    """Собрать MD и JSON с общим run_id. Возвращает пути обоих файлов.

    verdict_data — словарь по схеме ТЗ §9 (run_id, object, goal, preflight_summary,
    findings, verdict, scores, expert_disagreements, checked_areas,
    unchecked_areas, limitations, recommendations, token_stats,
    accepted_risks, retention_until, schema_version).
    """
    problems = _validate(verdict_data)
    if problems:
        raise SchemaError("; ".join(problems))
    data = post_mask(copy.deepcopy(verdict_data))
    now = datetime.now(timezone.utc)
    data.setdefault("created_utc", now.isoformat(timespec="seconds"))
    data.setdefault("schema_version", SCHEMA_VERSION)
    if not data.get("retention_until"):
        data["retention_until"] = (now + timedelta(days=int(retention_days))).date().isoformat()
    run_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(data["run_id"]))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{run_id}.json"
    md_path = out / f"{run_id}.md"
    # оба формата — сначала в памяти, запись только после успешного рендеринга
    # обоих: ошибка формирования не оставляет частично записанный отчёт
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    md_text = _render_md(data)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    return str(md_path), str(json_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборка отчётов MD+JSON (ТЗ §13)")
    parser.add_argument("--input", required=True, help="JSON с данными вердикта (схема ТЗ §9)")
    parser.add_argument("--out-dir", required=True, help="D:\\expert-panel\\reports")
    parser.add_argument("--retention-days", type=int, default=None,
                        help="срок хранения отчёта в днях (по умолчанию 90; "
                             "env EXPERT_PANEL_RETENTION_DAYS, пустое значение = дефолт)")
    args = parser.parse_args()

    try:
        verdict_data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except Exception as e:
        _emit({"status": "error", "reason": "не удалось прочитать входной JSON: " + str(e)})
        sys.exit(2)
    if not isinstance(verdict_data, dict):
        _emit({"status": "error", "reason": "входной JSON должен быть объектом"})
        sys.exit(2)
    retention = args.retention_days if args.retention_days is not None else _env_default()
    try:
        md_path, json_path = build(verdict_data, args.out_dir, retention)
    except SchemaError as e:
        _emit({"status": "invalid_schema", "reason": str(e)})
        sys.exit(2)
    _emit({"status": "ok", "md": md_path, "json": json_path})


if __name__ == "__main__":
    main()

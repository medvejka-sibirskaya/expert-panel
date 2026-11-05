"""Тесты 5, 7 (spec-etap0.md): пост-маска в отчёте, пустой env → дефолт 90.
Тест по ревью Жоры №4 (п. 4.4): preflight_summary не объект → invalid_schema,
ни одного файла отчёта не создаётся."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import report


def _minimal_verdict() -> dict:
    return {
        "run_id": "t-run-1",
        "object": {"type": "резюме",
                   "materials": [{"o_name": "O1", "format": "md", "size": "1 КБ"}]},
        "goal": "тест",
        "preflight_summary": {"experts": [], "models": [], "depth": "тест"},
        "findings": [{"id": "F-1", "priority": "Важно", "type": "подтверждённая",
                      "location": "O1, [абзац 1]", "evidence": "цитата",
                      "problem": "проблема", "consequence": "следствие",
                      "recommendation": "рекомендация", "confidence": "высокая"}],
        "verdict": "Принято с замечаниями",
        "scores": {"критерий": 3},
        "checked_areas": ["x"],
        "unchecked_areas": [],
        "limitations": [],
        "recommendations": [],
        "token_stats": {"input": "1k", "note": "оценка"},
    }


# Тест 5 — Пост-маска в отчёте: email и пароль из замечаний пойманы в md и json
def test_post_mask_in_report(tmp_path):
    verdict = _minimal_verdict()
    verdict["findings"][0]["evidence"] = "в резюме почта synth@example.com"
    verdict["findings"][0]["problem"] = "утёк password=SYNTH-PASS-77"

    out_dir = tmp_path / "out"
    md_path, json_path = report.build(verdict, str(out_dir))
    assert md_path.endswith("t-run-1.md")
    assert json_path.endswith("t-run-1.json")

    md_text = (tmp_path / "out" / "t-run-1.md").read_text(encoding="utf-8")
    json_text = (tmp_path / "out" / "t-run-1.json").read_text(encoding="utf-8")
    for text, label in ((md_text, "md"), (json_text, "json")):
        assert "[EMAIL]" in text, label
        assert "[СЕКРЕТ:password]" in text, label
        assert "synth@example.com" not in text, label
        assert "SYNTH-PASS" not in text, label


# Тест 7 — Пустой env EXPERT_PANEL_RETENTION_DAYS → дефолт 90 дней
def test_empty_env_default_retention(tmp_path, run_cli):
    verdict_path = tmp_path / "verdict.json"
    verdict_path.write_text(json.dumps(_minimal_verdict(), ensure_ascii=False),
                            encoding="utf-8")
    res = run_cli("report.py", "--input", verdict_path, "--out-dir", tmp_path / "out",
                  env_extra={"EXPERT_PANEL_RETENTION_DAYS": ""})
    out = json.loads(res.stdout)
    assert res.returncode == 0, res.stderr
    assert out["status"] == "ok"

    data = json.loads((tmp_path / "out" / "t-run-1.json").read_text(encoding="utf-8"))
    expected = (datetime.now(timezone.utc) + timedelta(days=90)).date()
    assert data["retention_until"] == expected.isoformat()


# Ревью Жоры №4, п. 4.4 — preflight_summary строкой: invalid_schema, файлов нет
def test_preflight_summary_must_be_object_no_partial_files(tmp_path):
    verdict = _minimal_verdict()
    verdict["preflight_summary"] = "строка вместо объекта"
    out_dir = tmp_path / "out"

    with pytest.raises(report.SchemaError):
        report.build(verdict, str(out_dir))

    assert not out_dir.exists() or not any(out_dir.iterdir())

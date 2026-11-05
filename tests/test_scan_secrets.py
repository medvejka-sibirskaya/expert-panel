"""Тесты 3, 4, 6 (spec-etap0.md): тишина сканера, маска контактов, work до prepare."""
from __future__ import annotations

import json

SYNTH_TEXT = "\n".join([
    "Секрет: Bearer SYNTH-BEARER-TOKEN-42",
    "Токен: token=SYNTH-TOKEN-42",
    "Ключ: api_key=SYNTH-KEY-AAA-1",
    "Почта: synth@example.com",
    "Телефон: +7 912 345 67 89",
    "Адрес: ул. Синтетическая, д. 7",
])


def _make_md(path, text: str = SYNTH_TEXT) -> None:
    path.write_text(text, encoding="utf-8")


# Тест 3 — Тишина сканера: значения секретов/ПД не в stdout/stderr
def test_scanner_silent(tmp_path, run_cli):
    md = tmp_path / "O1.md"
    _make_md(md)
    res = run_cli("scan_secrets.py", "scan", "--o-name", "O1", "--path", md)
    out = json.loads(res.stdout)
    assert res.returncode == 0, res.stderr
    assert out["status"] == "ok"
    assert out["o_name"] == "O1"
    findings = out["findings"]

    for value in ("SYNTH-BEARER", "SYNTH-TOKEN", "synth@example.com",
                  "912", "Синтетическая"):
        assert value not in res.stdout, value
        assert value not in res.stderr, value

    categories = {f["category"] for f in findings}
    assert {"secret", "contact_pii"} <= categories
    kinds = {f["kind"] for f in findings}
    assert {"bearer", "token", "email", "phone", "address"} <= kinds
    for f in findings:
        assert set(f) == {"o_name", "anchor", "kind", "category"}, f
        assert f["o_name"] == "O1"


# Тест 4 — Контакты замаскированы в копии (prepare --mode mask)
def test_contacts_masked_in_copy(tmp_path, run_cli):
    md = tmp_path / "O1.md"
    _make_md(md)
    work = tmp_path / "work" / "run-mask"
    res = run_cli("scan_secrets.py", "prepare", "--o-name", "O1", "--path", md,
                  "--mode", "mask", "--work-dir", work)
    out = json.loads(res.stdout)
    assert res.returncode == 0, res.stderr
    assert out["status"] == "ok"

    copy_path = work / "O1.md"
    text = copy_path.read_text(encoding="utf-8")
    assert "[EMAIL]" in text
    assert "[ТЕЛЕФОН]" in text
    assert "[АДРЕС]" in text
    assert "[СЕКРЕТ:api_key]" in text  # маска вида [СЕКРЕТ:вид]
    for value in ("synth@example.com", "912 345", "Синтетическая", "SYNTH-"):
        assert value not in text, value


# Тест 6 — До prepare в work нет файлов
def test_work_dir_empty_until_prepare(tmp_path, run_cli):
    md = tmp_path / "O1.md"
    _make_md(md, "Секрет: token=SYNTH-TOKEN-42")
    work = tmp_path / "work" / "run-abc"

    res = run_cli("scan_secrets.py", "scan", "--o-name", "O1", "--path", md)
    out = json.loads(res.stdout)
    assert res.returncode == 0, res.stderr
    assert out["status"] == "ok"
    assert not work.exists() or not any(work.iterdir()), "scan создал файлы в work"

    res2 = run_cli("scan_secrets.py", "prepare", "--o-name", "O1", "--path", md,
                   "--mode", "exclude", "--work-dir", work)
    out2 = json.loads(res2.stdout)
    assert res2.returncode == 0, res2.stderr
    assert out2["status"] == "ok"
    files = [p.name for p in work.iterdir()]
    assert files == ["O1.md"]

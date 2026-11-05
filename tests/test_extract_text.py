"""Тесты 1–2 (spec-etap0.md): извлечение текста из контейнеров, честный статус."""
from __future__ import annotations

import json

from pypdf import PdfWriter

from conftest import FIXTURES


def _make_docx(path, text: str) -> None:
    import docx

    document = docx.Document()
    document.add_paragraph(text)
    document.save(str(path))


def _make_xlsx(path, text: str) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active["A1"] = text
    wb.save(str(path))


# Тест 1 — Секрет в docx/xlsx/pdf обнаруживается
def test_secrets_found_in_docx_xlsx_pdf(tmp_path, run_cli):
    cases = [
        ("secret.docx", lambda p: _make_docx(p, "api_key=SYNTH-KEY-ABC-777"),
         "api_key", "SYNTH-KEY"),
        ("secret.xlsx", lambda p: _make_xlsx(p, "password=SYNTH-PASS-55"),
         "password", "SYNTH-PASS"),
        ("secret.pdf", None, "api_key", "SYNTH-KEY"),
    ]
    for name, maker, expected_kind, leaked_value in cases:
        path = tmp_path / name
        if maker is None:
            assert (FIXTURES / "secret.pdf").is_file(), "нет фикстуры secret.pdf"
            path = FIXTURES / "secret.pdf"
        else:
            maker(path)

        res = run_cli("scan_secrets.py", "scan", "--o-name", "O1", "--path", path)
        out = json.loads(res.stdout)
        assert res.returncode == 0, res.stderr
        assert out["status"] == "ok"
        assert out["findings"], f"{name}: находок нет"
        kinds = [f["kind"] for f in out["findings"]]
        assert expected_kind in kinds, f"{name}: kind {expected_kind} не найден"
        assert all(f["category"] == "secret" for f in out["findings"]
                   if f["kind"] in ("api_key", "password")), name
        leaked = (leaked_value in res.stdout) or (leaked_value in res.stderr)
        assert not leaked, f"{name}: значение попало в вывод сканера"


# Тест 2 — PDF без текстового слоя → «не проверено на секреты»
def test_blank_pdf_not_extractable(tmp_path, run_cli):
    blank = tmp_path / "blank.pdf"
    w = PdfWriter()
    w.add_blank_page(612, 792)
    with open(blank, "wb") as f:
        w.write(f)

    res = run_cli("scan_secrets.py", "scan", "--o-name", "O1",
                  "--path", tmp_path / "blank.pdf")
    out = json.loads(res.stdout)
    assert res.returncode == 1
    assert out["status"] == "not_extractable"
    assert out["note"] == "не проверено на секреты"

    res2 = run_cli("extract_text.py", tmp_path / "blank.pdf", "--json")
    out2 = json.loads(res2.stdout)
    assert res2.returncode == 1
    assert out2["status"] == "not_extractable"

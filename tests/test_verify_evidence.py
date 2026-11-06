"""Тесты verify_evidence.py: сверка цитаты по заявленному диапазону строк (ответ Жоры №10)."""
from __future__ import annotations

import json

import verify_evidence as ve

COPY = ("Alpha beta gamma delta\n"
        "Gamma delta epsilon zeta\n"
        "Omega omega omega omega\n")


def finding(evidence, location=None, o_name="O1", fid="F-1"):
    f = {"id": fid, "o_name": o_name, "evidence": evidence}
    if location is not None:
        f["location"] = location
    return f


def test_in_range_verified():
    res = ve.verify_finding(finding("Gamma delta epsilon", "O1, строки 2–2"), {"O1": COPY})
    assert res["result"] == "verified"


def test_out_of_range_mismatch_with_actual_lines():
    res = ve.verify_finding(finding("Alpha beta gamma", "O1, строки 3–3"), {"O1": COPY})
    assert res["result"] == "mismatch"
    assert "вне заявленного диапазона" in res["reason"]
    assert "строки 1" in res["reason"]


def test_single_line_exploit_line999():
    # сценарий ревьюера: location указывает строку 999, цитата в строке 1
    res = ve.verify_finding(finding("Alpha beta gamma", "O1, строка 999"), {"O1": COPY})
    assert res["result"] == "mismatch"
    assert "вне заявленного диапазона" in res["reason"]


def test_crlf_no_false_mismatch():
    res = ve.verify_finding(
        finding("gamma delta / epsilon zeta", "O1, строки 1–2"),
        {"O1": COPY.replace("\n", "\r\n")})
    assert res["result"] == "verified"


def test_no_location_notes_unchecked():
    res = ve.verify_finding(finding("Alpha beta gamma delta"), {"O1": COPY})
    assert res["result"] == "verified"
    assert res["reason"] == "расположение не проверено"


def test_location_without_range_treated_as_file():
    res = ve.verify_finding(finding("Omega omega omega", "O1, структура файла"), {"O1": COPY})
    assert res["result"] == "verified"
    assert res["reason"] == "расположение не проверено"


def test_multipart_one_fragment_outside():
    res = ve.verify_finding(finding("Alpha beta gamma / Omega omega omega",
                                    "O1, строки 1–2"), {"O1": COPY})
    assert res["result"] == "mismatch"
    assert "фрагмент 2" in res["reason"] and "строки 3" in res["reason"]


def test_multipart_all_in_range():
    res = ve.verify_finding(finding("Alpha beta gamma / Gamma delta epsilon",
                                    "O1, строки 1–2"), {"O1": COPY})
    assert res["result"] == "verified"


def test_o_name_missing():
    res = ve.verify_finding(finding("Alpha beta gamma"), {})
    assert res["result"] == "mismatch"
    assert "манифест" in res["reason"]


def test_short_fragment_unverifiable():
    res = ve.verify_finding(finding("abc / Gamma delta epsilon"), {"O1": COPY})
    assert res["result"] == "unverifiable"


def test_lo_gt_hi_unverifiable():
    res = ve.verify_finding(finding("Alpha beta gamma", "O1, строки 5–2"), {"O1": COPY})
    assert res["result"] == "unverifiable"


def test_range_given_quote_absent_keeps_old_reason():
    res = ve.verify_finding(finding("Nicht vorhanden hier", "O1, строки 1–3"), {"O1": COPY})
    assert res["result"] == "mismatch"
    assert "не найдена в указанном файле" in res["reason"]


def test_cli_end_to_end(run_cli, tmp_path):
    (tmp_path / "O1.md").write_text(COPY, encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"O1": "O1.md"}, ensure_ascii=False), encoding="utf-8")
    findings = {"findings": [finding("Gamma delta epsilon", "O1, строки 2–2", fid="F-1"),
                             finding("Alpha beta gamma", "O1, строка 999", fid="F-2")]}
    (tmp_path / "findings.json").write_text(
        json.dumps(findings, ensure_ascii=False), encoding="utf-8")
    p = run_cli("verify_evidence.py", "--findings", tmp_path / "findings.json",
                "--manifest", tmp_path / "manifest.json")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["status"] == "ok"
    assert out["summary"] == {"verified": 1, "mismatch": 1, "unverifiable": 0}

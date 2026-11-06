"""Тесты check_numbers.py: покрытия пресетов default и resume (пробел был найден ревью Жоры №10)."""
from __future__ import annotations

import check_numbers as cn


def checks(text, preset="default", o_name="O1"):
    return cn.check(o_name, text, preset)


def test_sum_ok_no_findings():
    assert checks("Итого: 10 + 5 = 15") == []


def test_sum_mismatch_detected():
    fs = checks("Итого: 10 + 5 = 16")
    assert len(fs) == 1
    assert fs[0]["check"] == "sum_mismatch"
    assert "не сходится" in fs[0]["result"]


def test_invalid_date_detected():
    fs = checks("Дата: 31.02.2024")
    assert [f["check"] for f in fs] == ["date_invalid"]


def test_date_order_detected():
    fs = checks("Период с 05.03.2024 по 01.03.2024")
    assert [f["check"] for f in fs] == ["date_order"]
    assert "конец раньше начала" in fs[0]["result"]


def test_numbering_duplicate_and_gap():
    dup = checks("1. альфа\n2. бета\n2. гамма")
    assert [f["check"] for f in dup] == ["numbering_duplicate"]
    gap = checks("1. альфа\n3. гамма")
    assert [f["check"] for f in gap] == ["numbering_gap"]


def test_resume_preset_staged_mismatch():
    text = ("Опыт: общий опыт работы 5 лет.\n"
            "2019–2022 — ООО «Ромашка», маркетолог\n"
            "2022–2026 — ИП Петров, ведущий специалист\n")
    fs = checks(text, preset="resume")
    assert [f["check"] for f in fs] == ["experience_sum_mismatch"]
    assert fs[0]["result"].startswith("заявлено 5 лет")


def test_resume_preset_consistent_no_findings():
    text = ("Опыт: общий опыт работы 7 лет.\n"
            "2019–2022 — ООО «Ромашка»\n"
            "2022–2026 — ИП Петров\n")
    assert checks(text, preset="resume") == []


def test_resume_preset_half_period_warned():
    text = "Общий стаж 2 года.\n2019–2021 — ООО «Ромашка»\nс 2023–\n"
    fs = checks(text, preset="resume")
    assert [f["check"] for f in fs] == ["experience_period_uncounted"]


def test_default_preset_skips_experience():
    text = "Общий опыт работы 5 лет.\n2019–2022 — ООО «Ромашка»\n2022–2026 — ИП Петров\n"
    assert checks(text, preset="default") == []

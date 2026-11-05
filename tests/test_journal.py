"""Тесты 8–13 (spec-etap0.md): lock, остатки work, ремонт и идемпотентность журнала."""
from __future__ import annotations

import ctypes
import json
import os
import subprocess


def _history(root):
    return root / "history" / "history.jsonl"


def _read_valid_events(root):
    return [json.loads(ln) for ln in _history(root).read_text(encoding="utf-8").splitlines()
            if ln.strip()]


def _quarantine_lines(root):
    q = root / "history" / "history.quarantine"
    if not q.exists():
        return []
    return [ln for ln in q.read_text(encoding="utf-8").splitlines() if ln.strip()]


# Тест 8 — Двойной запуск → отказ по lock
def test_second_run_refused(tmp_path, journal):
    locked = journal("lock", "--run-id", "r1", "--pid", os.getpid(), root=tmp_path)
    assert json.loads(locked.stdout)["status"] == "locked"

    second = journal("lock", "--run-id", "r2", root=tmp_path)
    assert second.returncode == 2, second.stdout
    assert json.loads(second.stdout)["status"] == "refused"


def _pid_alive(pid: int) -> bool:
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def _dead_pid() -> int:
    """PID гарантированно мёртвого процесса: pid после короткоживущего cmd,
    с ретраями (система может переиспользовать pid мгновенно)."""
    for _ in range(20):
        p = subprocess.Popen(["cmd", "/c", "exit"])
        p.wait()
        if not _pid_alive(p.pid):
            return p.pid
    # fallback: заведомо незанятый pid (Windows выдаёт кратные 4 с пробелами)
    pid = 100000
    while _pid_alive(pid):
        pid += 4
    return pid


# Тест 9 — Lock мёртвого pid → снятие по подтверждению
def test_stale_lock_confirm(tmp_path, journal):
    dead_pid = _dead_pid()

    first = journal("lock", "--run-id", "old", "--pid", dead_pid, root=tmp_path)
    assert json.loads(first.stdout)["status"] == "locked"
    before = (tmp_path / "run.lock").read_text(encoding="utf-8")

    stale = journal("lock", "--run-id", "r1", root=tmp_path)
    assert stale.returncode == 2, stale.stdout
    assert json.loads(stale.stdout)["status"] == "stale_lock"
    assert (tmp_path / "run.lock").read_text(encoding="utf-8") == before, \
        "lock пересоздан без --confirm-stale"

    confirmed = journal("lock", "--run-id", "r1", "--confirm-stale", root=tmp_path)
    out = json.loads(confirmed.stdout)
    assert confirmed.returncode == 0, confirmed.stderr
    assert out["status"] == "locked"
    assert out["run_id"] == "r1"


# Тест 10 — Остатки work: found без флага, удаление по --confirm-delete
def test_work_remains(tmp_path, journal):
    work = tmp_path / "work"
    (work / "a1").mkdir(parents=True)
    (work / "a2").mkdir()

    found = journal("remains", root=tmp_path)
    out = json.loads(found.stdout)
    assert found.returncode == 0, found.stderr
    assert out["status"] == "found"
    assert out["dirs"] == ["a1", "a2"]
    assert (work / "a1").is_dir() and (work / "a2").is_dir()

    deleted = journal("remains", "--confirm-delete", root=tmp_path)
    out2 = json.loads(deleted.stdout)
    assert deleted.returncode == 0, deleted.stderr
    assert out2["status"] == "deleted"
    assert not (work / "a1").exists() and not (work / "a2").exists()


# Тест 11 — Повреждённый хвост → quarantine с repair_id + journal_repaired
def test_damaged_tail_repair(tmp_path, journal):
    journal("append", "--run-id", "r1", "--event-id", "e1", "--type", "run_started",
            root=tmp_path)
    journal("append", "--run-id", "r1", "--event-id", "e2", "--type",
            "preflight_shown", root=tmp_path)
    checked = journal("check", root=tmp_path)
    assert json.loads(checked.stdout) == {"status": "ok", "events": 2}

    # обрывок без \n в конце файла
    with open(_history(tmp_path), "a", encoding="utf-8") as f:
        f.write('{"seq":3,"run_id":"r1"')

    broken = journal("check", root=tmp_path)
    assert broken.returncode == 4, broken.stdout
    assert json.loads(broken.stdout)["status"] == "invalid"

    no_confirm = journal("repair", root=tmp_path)
    assert no_confirm.returncode == 2, no_confirm.stdout
    assert json.loads(no_confirm.stdout)["status"] == "confirm_required"

    confirmed = journal("repair", "--confirm", root=tmp_path)
    out = json.loads(confirmed.stdout)
    assert confirmed.returncode == 0, confirmed.stderr
    assert out["status"] == "repaired"
    repair_id = out["repair_id"]

    rechecked = journal("check", root=tmp_path)
    assert rechecked.returncode == 0, rechecked.stdout
    assert json.loads(rechecked.stdout)["status"] == "ok"

    # quarantine: заголовок с repair_id + перенесённая повреждённая строка
    q_lines = _quarantine_lines(tmp_path)
    headers = [json.loads(ln) for ln in q_lines if "quarantine_header" in ln]
    assert headers and headers[0].get("repair_id") == repair_id

    events = _read_valid_events(tmp_path)
    repaired_events = [ev for ev in events if ev["type"] == "journal_repaired"]
    assert len(repaired_events) == 1
    assert repaired_events[0]["data"]["repair_id"] == repair_id

    # seq восстановлен: макс. валидный 3 + 1
    nxt = journal("append", "--run-id", "r1", "--event-id", "e3", "--type",
                  "preflight_approved", root=tmp_path)
    assert json.loads(nxt.stdout)["seq"] == 4


# Тест 12 — Незакрытый перенос → только запись события, quarantine не трогается
def test_unclosed_transfer_event_only(tmp_path, journal):
    journal("append", "--run-id", "r1", "--event-id", "e1", "--type", "run_started",
            root=tmp_path)

    q = tmp_path / "history" / "history.quarantine"
    q.parent.mkdir(parents=True, exist_ok=True)
    header = {"type": "quarantine_header", "repair_id": "R-SPEC-12",
              "utc_ts": "x", "seq": 1, "reason": "тест"}
    with open(q, "a", encoding="utf-8") as f:
        f.write(json.dumps(header, ensure_ascii=False) + "\n")
    before = len(_quarantine_lines(tmp_path))

    checked = journal("check", root=tmp_path)
    assert checked.returncode == 4, checked.stdout
    assert json.loads(checked.stdout)["status"] == "invalid"

    confirmed = journal("repair", "--confirm", root=tmp_path)
    out = json.loads(confirmed.stdout)
    assert confirmed.returncode == 0, confirmed.stderr
    assert out["status"] == "repaired"
    assert out["moved_lines"] == 0
    assert out["repair_id"] == "R-SPEC-12"

    assert len(_quarantine_lines(tmp_path)) == before, "quarantine вырос"

    events = journal("list", root=tmp_path)
    listed = json.loads(events.stdout)["events"]
    assert len(listed) == 2  # run_started + journal_repaired

    repaired_events = [ev for ev in _read_valid_events(tmp_path)
                       if ev["type"] == "journal_repaired"]
    assert len(repaired_events) == 1
    assert repaired_events[0]["data"]["repair_id"] == "R-SPEC-12"

    rechecked = journal("check", root=tmp_path)
    assert rechecked.returncode == 0, rechecked.stdout
    assert json.loads(rechecked.stdout)["status"] == "ok"


# Тест 13 — Дубль event_id → явная ошибка
def test_duplicate_event_id(tmp_path, journal):
    first = journal("append", "--run-id", "r1", "--event-id", "e1", "--type",
                    "run_started", root=tmp_path)
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["status"] == "ok"

    dup = journal("append", "--run-id", "r1", "--event-id", "e1", "--type",
                  "run_started", root=tmp_path)
    assert dup.returncode == 3, dup.stdout
    assert json.loads(dup.stdout)["status"] == "duplicate_event_id"

    listed = journal("list", root=tmp_path)
    events = json.loads(listed.stdout)["events"]
    assert len(events) == 1, "дубль записан в журнал"

    checked = journal("check", root=tmp_path)
    assert checked.returncode == 0, checked.stdout
    assert json.loads(checked.stdout)["status"] == "ok"

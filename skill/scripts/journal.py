"""Журнал комиссии: append-only JSONL, lock, проверка целостности (ТЗ §10, §13).

Файл: D:\\expert-panel\\history\\history.jsonl
Идентификаторы: run_id (UUID запуска) + event_id (уникальный) + seq (глобальный).
Гарантии:
- запись — одна полная строка за вызов, с \\n и flush;
- повтор того же event_id — явная ошибка (идемпотентность);
- повреждённый хвост не трогается молча: перенос в history.quarantine
  с заголовком {repair_id, utc_ts, seq, причина} + запись journal_repaired
  с тем же repair_id — ТОЛЬКО по подтверждению; автоматически — только
  хвостовой блок, повреждение в середине — отказ и ручной разбор (exit 5);
  если событие записать не удалось, check видит незакрытый перенос
  и повторяет только запись события;
- ПД и исходные пути в журнал не пишутся — только O-имена;
- lock: run.lock (PID + run_id) — эвристический признак активности запуска,
  не доказательство: координатор передаёт --pid долгоживущего владельца
  (живой чужой PID → отказ; мёртвый → снятие по подтверждению); обнаружение
  остатков work\\ от незавершённых запусков.

Пути берутся из --root (CLI), env EXPERT_PANEL_ROOT или дефолта D:\\expert-panel
(пустое значение env игнорируется — работают дефолты).

СТАТУС РЕАЛИЗАЦИИ: этап 0.2 — реализовано; тестируется тестами 8–13 (tests/README.md).
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path(r"D:\expert-panel")

EVENT_TYPES = {
    "run_started", "preflight_shown", "preflight_approved", "finding_detected",
    "phase_experts_started", "expert_finished", "checkpoint_passed", "judge_finished",
    "report_saved", "risk_accepted_by_user", "retention_cleanup_proposed",
    "report_deleted", "run_finished", "run_stopped", "journal_repaired",
}


class DuplicateEvent(Exception):
    """Повторная запись того же event_id — отвергается явно (ТЗ §10)."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _pid_alive(pid) -> bool:
    """True — процесс существует. Не удалось проверить — считаем живым (безопаснее)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class Paths:
    def __init__(self, root: Path):
        self.root = root
        self.history = root / "history" / "history.jsonl"
        self.quarantine = root / "history" / "history.quarantine"
        self.work = root / "work"
        self.lock = root / "run.lock"


def _read_state(path: Path):
    """Журнал целиком: (строки, валидные [(№, событие)], повреждённые [(№, сырая строка)])."""
    if not path.exists():
        return [], [], []
    raw = path.read_text(encoding="utf-8", errors="replace")
    ends_nl = raw.endswith("\n")
    lines = raw.split("\n")
    if ends_nl and lines and lines[-1] == "":
        lines.pop()
    valid: list[tuple[int, dict]] = []
    damaged: list[tuple[int, str]] = []
    for i, ln in enumerate(lines, 1):
        if not ln.strip():
            continue
        try:
            ev = json.loads(ln)
            if not isinstance(ev, dict):
                raise ValueError("не объект")
            valid.append((i, ev))
        except Exception:
            damaged.append((i, ln))
    if not ends_nl and lines and lines[-1].strip():
        # неполная последняя строка (файл оборван без \n) — повреждена,
        # даже если распарсилась: запись обязана быть полной строкой
        if valid and valid[-1][0] == len(lines):
            i, _ev = valid.pop()
            damaged.append((i, lines[-1]))
    return lines, valid, damaged


def _read_quarantine(p: Paths) -> tuple[list[str], list[dict]]:
    """(repair_id заголовков, все записи quarantine)."""
    if not p.quarantine.exists():
        return [], []
    headers: list[str] = []
    entries: list[dict] = []
    for ln in p.quarantine.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ln.strip():
            continue
        try:
            entry = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        entries.append(entry)
        if entry.get("type") == "quarantine_header" and entry.get("repair_id"):
            headers.append(entry["repair_id"])
    return headers, entries


def _max_seq(valid: list[tuple[int, dict]]) -> int:
    return max((ev.get("seq", 0) for _, ev in valid
                if isinstance(ev.get("seq"), int)), default=0)


def _append_event(p: Paths, run_id: str, event_id: str, type_: str, data: dict,
                  utc_ts: str | None = None) -> dict:
    """Одна полная строка с \\n и flush; глобальный seq = максимальный валидный + 1."""
    _, valid, _ = _read_state(p.history)
    for _, ev in valid:
        if ev.get("event_id") == event_id:
            raise DuplicateEvent(
                f"event_id уже записан (seq={ev.get('seq')}) — повтор отвергнут")
    event = {"seq": _max_seq(valid) + 1, "run_id": run_id, "event_id": event_id,
             "type": type_, "utc_ts": utc_ts or _utc(), "data": data}
    p.history.parent.mkdir(parents=True, exist_ok=True)
    with open(p.history, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
        f.flush()
    return event


def _rewrite_history_without(p: Paths, damaged_indexes: set[int], lines: list[str]) -> None:
    keep = [ln for i, ln in enumerate(lines, 1) if i not in damaged_indexes]
    text = "\n".join(keep) + "\n" if keep else ""
    tmp = p.history.with_suffix(".jsonl.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p.history)


def _quarantine_append(p: Paths, entry: dict) -> None:
    p.quarantine.parent.mkdir(parents=True, exist_ok=True)
    with open(p.quarantine, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        f.flush()


def _check_problems(p: Paths) -> tuple[list[str], int]:
    lines, valid, damaged = _read_state(p.history)
    problems: list[str] = []
    if damaged:
        max_valid_i = max((i for i, _ in valid), default=0)
        min_damaged_i = min(i for i, _ in damaged)
        middle = max_valid_i > min_damaged_i
        hint = ("ручной разбор: автоматический repair запрещён — повреждение "
                "в середине журнала" if middle else
                "перенос в quarantine через repair --confirm")
        for i, _ln in damaged:
            problems.append(
                f"строка {i}: повреждена (не парсится как JSON или оборвана "
                f"без \\n) — {hint}")
    seqs = [ev.get("seq") for _, ev in valid]
    if any(not isinstance(s, int) for s in seqs):
        problems.append("seq: есть события без целочисленного seq")
    else:
        expected = list(range(1, len(valid) + 1))
        if sorted(seqs) != expected:
            problems.append(f"seq не непрерывен: событий {len(valid)}, "
                            f"последовательность {sorted(seqs)[:10]}…")
    seen: dict[str, int] = {}
    for i, ev in valid:
        eid = ev.get("event_id")
        if not eid:
            problems.append(f"строка {i}: событие без event_id")
            continue
        if eid in seen:
            problems.append(f"event_id дублируется: {eid} (строки {seen[eid]} и {i})")
        else:
            seen[eid] = i
    started = {ev.get("run_id") for _, ev in valid if ev.get("type") == "run_started"}
    for i, ev in valid:
        if ev.get("type") == "journal_repaired":
            continue  # системное событие ремонта — run_started не требуется
        if ev.get("run_id") not in started:
            problems.append(f"строка {i}: run_id {ev.get('run_id')} без события run_started")
    headers, _ = _read_quarantine(p)
    repaired = {ev.get("data", {}).get("repair_id") for _, ev in valid
                if ev.get("type") == "journal_repaired" and isinstance(ev.get("data"), dict)}
    for rid in headers:
        if rid not in repaired:
            problems.append(
                f"перенос не закрыт: repair_id {rid} (journal_repaired не найден) — "
                "повторите repair --confirm: он запишет только событие, без повторного переноса")
    return problems, len(valid)


def cmd_lock(p: Paths, args) -> None:
    if p.lock.exists():
        try:
            old = json.loads(p.lock.read_text(encoding="utf-8"))
        except Exception:
            old = {"pid": -1, "run_id": None}
        old_pid = old.get("pid", -1)
        if _pid_alive(old_pid):
            _emit({"status": "refused", "reason": "активный запуск (lock жив)",
                   "run_id": old.get("run_id"), "pid": old_pid})
            sys.exit(2)
        if not args.confirm_stale:
            _emit({"status": "stale_lock", "reason": "lock мёртвого процесса",
                   "run_id": old.get("run_id"), "pid": old_pid,
                   "hint": "снятие — по подтверждению: повторите с --confirm-stale"})
            sys.exit(2)
    run_id = args.run_id or str(uuid.uuid4())
    # pid живого владельца запуска (по умолчанию — сам вызвавший процесс)
    pid = args.pid if args.pid is not None else os.getpid()
    p.lock.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.lock.with_suffix(".lock.tmp")
    tmp.write_text(json.dumps({"pid": pid, "run_id": run_id, "utc_ts": _utc()},
                              ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p.lock)
    _emit({"status": "locked", "run_id": run_id, "pid": pid})


def cmd_unlock(p: Paths, args) -> None:
    if not p.lock.exists():
        _emit({"status": "no_lock"})
        return
    try:
        old = json.loads(p.lock.read_text(encoding="utf-8"))
    except Exception:
        old = {}
    if args.run_id and old.get("run_id") != args.run_id:
        _emit({"status": "refused", "reason": "lock принадлежит другому запуску",
               "lock_run_id": old.get("run_id")})
        sys.exit(2)
    p.lock.unlink()
    _emit({"status": "unlocked", "run_id": old.get("run_id")})


def cmd_append(p: Paths, args) -> None:
    if args.type not in EVENT_TYPES:
        _emit({"status": "error", "reason": "неизвестный тип события: " + str(args.type)})
        sys.exit(2)
    if not args.run_id or not args.event_id:
        _emit({"status": "error", "reason": "нужны --run-id и --event-id"})
        sys.exit(2)
    try:
        data = json.loads(args.data) if args.data else {}
    except json.JSONDecodeError as e:
        _emit({"status": "error", "reason": "--data не JSON: " + str(e)})
        sys.exit(2)
    if not isinstance(data, dict):
        _emit({"status": "error", "reason": "--data должен быть JSON-объектом"})
        sys.exit(2)
    try:
        ev = _append_event(p, args.run_id, args.event_id, args.type, data, args.utc_ts)
    except DuplicateEvent as e:
        _emit({"status": "duplicate_event_id", "reason": str(e)})
        sys.exit(3)
    _emit({"status": "ok", "seq": ev["seq"]})


def cmd_list(p: Paths, args) -> None:
    _, valid, _ = _read_state(p.history)
    events = [{"seq": ev.get("seq"), "run_id": ev.get("run_id"), "type": ev.get("type")}
              for _, ev in valid]
    _emit({"status": "ok", "events": events})


def cmd_read(p: Paths, args) -> None:
    _, valid, _ = _read_state(p.history)
    events = [ev for _, ev in valid if ev.get("run_id") == args.run_id]
    _emit({"status": "ok", "run_id": args.run_id, "events": events})


def cmd_check(p: Paths, args) -> None:
    problems, count = _check_problems(p)
    if problems:
        _emit({"status": "invalid", "events": count, "problems": problems})
        sys.exit(4)
    _emit({"status": "ok", "events": count})


def cmd_repair(p: Paths, args) -> None:
    lines, valid, damaged = _read_state(p.history)
    headers, _ = _read_quarantine(p)
    repaired = {ev.get("data", {}).get("repair_id") for _, ev in valid
                if ev.get("type") == "journal_repaired" and isinstance(ev.get("data"), dict)}
    unclosed = [rid for rid in headers if rid not in repaired]
    if not damaged and not unclosed:
        _emit({"status": "nothing_to_do"})
        return
    if damaged:
        # автоматически — только хвостовой блок; повреждение в середине
        # (после него есть валидные события) — ручной разбор
        max_valid_i = max((i for i, _ in valid), default=0)
        min_damaged_i = min(i for i, _ in damaged)
        if max_valid_i > min_damaged_i:
            _emit({"status": "manual_review_required",
                   "reason": "повреждение в середине журнала: после повреждённой "
                             "строки есть валидные события — автоматический repair "
                             "запрещён, нужен ручной разбор",
                   "damaged_lines": [i for i, _ in damaged]})
            sys.exit(5)
    if not args.confirm:
        _emit({"status": "confirm_required",
               "damaged_lines": [i for i, _ in damaged],
               "unclosed_transfers": unclosed,
               "hint": "перенос и запись journal_repaired — только по подтверждению: "
                       "повторите с --confirm"})
        sys.exit(2)
    # незакрытый перенос уже есть → quarantine не трогаем, повторяем ТОЛЬКО
    # недоделанное: перенос строк (если хвост ещё в журнале) и запись события
    repair_id = unclosed[0] if unclosed else str(uuid.uuid4())
    if damaged:
        if not unclosed:
            _quarantine_append(p, {"type": "quarantine_header", "repair_id": repair_id,
                                   "utc_ts": _utc(), "seq": _max_seq(valid),
                                   "reason": "повреждённый хвост журнала"})
        for i, ln in damaged:
            _quarantine_append(p, {"type": "quarantine_line", "repair_id": repair_id,
                                   "raw": ln})
        _rewrite_history_without(p, {i for i, _ in damaged}, lines)
    _append_event(p, "system", str(uuid.uuid4()), "journal_repaired",
                  {"repair_id": repair_id, "moved_lines": len(damaged),
                   "note": "перенос повреждённого хвоста в quarantine"})
    _emit({"status": "repaired", "repair_id": repair_id, "moved_lines": len(damaged)})


def cmd_remains(p: Paths, args) -> None:
    """Остатки work\\ от незавершённых запусков: обнаружение — всегда,
    удаление — только по --confirm-delete."""
    dirs = sorted(d.name for d in p.work.iterdir() if d.is_dir()) if p.work.exists() else []
    if not dirs:
        _emit({"status": "clean"})
        return
    if args.confirm_delete:
        for name in dirs:
            shutil.rmtree(p.work / name)
        _emit({"status": "deleted", "dirs": dirs})
        return
    _emit({"status": "found", "dirs": dirs,
           "hint": "удаление — только по подтверждению: повторите с --confirm-delete"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Журнал JSONL: события, lock, целостность (ТЗ §13)")
    parser.add_argument("--root", default=None,
                        help="корень D:\\expert-panel (для тестов; иначе env EXPERT_PANEL_ROOT)")
    sub = parser.add_subparsers(dest="command", required=True)
    lock_p = sub.add_parser("lock", help="создать run.lock (PID + run_id); снятие мёртвого — --confirm-stale")
    lock_p.add_argument("--run-id", default=None)
    lock_p.add_argument("--pid", type=int, default=None,
                        help="PID живого владельца запуска (по умолчанию — текущий процесс)")
    lock_p.add_argument("--confirm-stale", action="store_true",
                        help="подтверждение снятия lock мёртвого процесса")
    unlock_p = sub.add_parser("unlock", help="снять run.lock (штатная остановка)")
    unlock_p.add_argument("--run-id", default=None)
    append_p = sub.add_parser("append", help="записать событие: run_id, event_id, тип, данные (без ПД)")
    append_p.add_argument("--run-id", required=True)
    append_p.add_argument("--event-id", required=True)
    append_p.add_argument("--type", required=True)
    append_p.add_argument("--data", default=None, help="JSON-объект с данными события")
    append_p.add_argument("--utc-ts", default=None)
    sub.add_parser("list", help="список событий (run_id, seq, тип)")
    read_p = sub.add_parser("read", help="прочитать события запуска по run_id")
    read_p.add_argument("--run-id", required=True)
    sub.add_parser("check", help="целостность: JSON-строки, seq непрерывен, event_id уникальны, переносы закрыты")
    repair_p = sub.add_parser("repair", help="перенос повреждённого хвоста в quarantine с repair_id — по подтверждению")
    repair_p.add_argument("--confirm", action="store_true")
    remains_p = sub.add_parser("remains", help="остатки work\\ от незавершённых запусков; удаление — --confirm-delete")
    remains_p.add_argument("--confirm-delete", action="store_true")
    args = parser.parse_args()

    root = args.root or os.environ.get("EXPERT_PANEL_ROOT") or ""  # пустой env = дефолт
    p = Paths(Path(root) if root else DEFAULT_ROOT)

    {"lock": lambda: cmd_lock(p, args),
     "unlock": lambda: cmd_unlock(p, args),
     "append": lambda: cmd_append(p, args),
     "list": lambda: cmd_list(p, args),
     "read": lambda: cmd_read(p, args),
     "check": lambda: cmd_check(p, args),
     "repair": lambda: cmd_repair(p, args),
     "remains": lambda: cmd_remains(p, args)}[args.command]()


if __name__ == "__main__":
    main()

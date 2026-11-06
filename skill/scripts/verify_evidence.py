"""Механическая сверка доказательств: цитата в указанном манифестом файле (ТЗ §13, ревью Жоры №4, п. 4.1; локация — по ответу Жоры №10).

verified проверяет привязку и локацию цитаты, но не семантическую
правильность замечания (ревью Жоры, 06.11).

Проверяет связь замечания с исходным доказательством. Это отдельная задача:
вычислимое — check_numbers.py, семантика — эксперты, а здесь — поиск
нормализованной цитаты замечания в физическом файле, который назначен
O-имени манифестом. Манифест — единственный источник соответствия
«O-имя → файл»: папка не листается, порядок файлов не угадывается.

Ничего не исправляет, не переписывает заключения, не принимает решений:
результаты — данные для координатора и судьи. mismatch = ненадёжное
доказательство (цитата не в заявленном файле): судья не подтверждает
такое замечание как «подтверждённое». unverifiable = механически
не проверяется (тоже не считается проверенным).

Вход:
  --findings   JSON: {"findings": [{"id": "...", "o_name": "O1",
                "evidence": "..."}]}; обязательны id, o_name, evidence,
                location — необязательный диапазон строк («строки 7–9» /
                «строка 7»); прочие поля замечания игнорируются
  --manifest   JSON: {"O1": "O1.md", ...}; пути относительно файла
                манифеста либо абсолютные

Выход: {"status": "ok", "results": [{"id", "o_name", "result", "reason"}],
"summary": {"verified", "mismatch", "unverifiable"}}. result: verified /
mismatch / unverifiable. Цитаты и содержимое файлов в вывод не попадают.

Нормализация ограниченная (пробелы/переносы, типографские кавычки/тире/
многоточия), без семантического поиска: похожие фразы совпадением
не считаются. Многочастные цитаты вида «фрагмент 1» / «фрагмент 2»:
сначала ищется вся цитата, затем фрагменты по отдельности —
verified только если нашлись все.

СТАТУС РЕАЛИЗАЦИИ: реализовано по ревью Жоры №4 (этап «до пилота»).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ограниченная нормализация: пробелы/переносы и типографика, БЕЗ семантики
_QUOTE_CHARS = "«»„“”\"'`"
_DASH_RE = re.compile(r"[–—−‒‑]")
_WS_RE = re.compile(r"\s+")
_PART_SPLIT_RE = re.compile(r"\s+/\s+")  # разделитель многочастных цитат
MIN_FRAGMENT_LEN = 4
# локация замечания: «строки 7–9» / «строка 7»; тире — любые из –—−-
_LOCATION_LINES_RE = re.compile(r"\bстрок[аи]\s+([^,\[\]\n]+)", re.IGNORECASE)
_LINE_RANGE_RE = re.compile(r"([0-9]+)\s*[–—−-]\s*([0-9]+)")


def _line_range(location: object) -> tuple[int, int] | None:
    """Диапазон строк из location: (lo, hi) включительно; None — диапазона нет."""
    if not isinstance(location, str):
        return None
    match = _LOCATION_LINES_RE.search(location)
    if not match:
        return None
    candidate = match.group(1).strip()
    span = _LINE_RANGE_RE.fullmatch(candidate)
    if span:
        lo, hi = map(int, span.groups())
        if lo < 1 or lo > hi:
            raise ValueError("некорректный диапазон строк: требуется 1 ≤ lo ≤ hi")
        return lo, hi
    if re.fullmatch(r"([0-9]+)", candidate):
        n = int(candidate)
        if n < 1:
            raise ValueError("некорректный диапазон строк: минимальный номер строки — 1")
        return n, n
    if re.search(r"[–—−-]", candidate):
        raise ValueError("некорректный диапазон строк: нужны два целых числа")
    return None


def _fragment_lines(fragment: str, lines: list[str]) -> str:
    """Фактические строки вхождения фрагмента (включая межстрочные)."""
    text = " ".join(lines)
    intervals: list[tuple[int, int, int]] = []
    offset = 0
    for number, line in enumerate(lines, 1):
        intervals.append((offset, offset + len(line), number))
        offset += len(line) + 1
    spans: list[str] = []
    pattern = re.escape(fragment).replace(r"\ ", r"\s+")
    for match in re.finditer(r"(?=(" + pattern + r"))", text):
        start, end = match.span(1)
        numbers = [number for left, right, number in intervals
                   if left < end and right > start]
        if not numbers:
            continue
        span = str(numbers[0]) if numbers[0] == numbers[-1] else f"{numbers[0]}–{numbers[-1]}"
        if span not in spans:
            spans.append(span)
    return ", ".join(spans)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _normalize(s: str) -> str:
    s = s.replace(" ", " ").replace(" ", " ").replace("…", "...")
    s = _DASH_RE.sub("-", s)
    s = "".join(ch for ch in s if ch not in _QUOTE_CHARS)
    return _WS_RE.sub(" ", s).strip()


def _fragments(evidence: str) -> list[str]:
    return [n for n in (_normalize(p) for p in _PART_SPLIT_RE.split(evidence)) if n]


def verify_finding(finding: dict, texts: dict[str, str]) -> dict:
    """Проверить одно замечание. texts: O-имя → исходный текст копии.

    location может задавать диапазон «строки X–Y» / «строка X»: цитата
    проверяется в заявленных строках; иначе — по всему файлу с пометкой
    «расположение не проверено» в reason."""
    fid = finding.get("id", "?")
    o_name = finding.get("o_name")
    evidence = finding.get("evidence")
    if not isinstance(o_name, str) or not o_name.strip():
        return {"id": fid, "o_name": "", "result": "unverifiable",
                "reason": "не указано O-имя"}
    if not isinstance(evidence, str) or not evidence.strip():
        return {"id": fid, "o_name": o_name, "result": "unverifiable",
                "reason": "нет цитаты (evidence)"}
    if o_name not in texts:
        return {"id": fid, "o_name": o_name, "result": "mismatch",
                "reason": "O-имя отсутствует в манифесте"}
    try:
        bounds = _line_range(finding.get("location"))
    except ValueError as exc:
        return {"id": fid, "o_name": o_name, "result": "unverifiable",
                "reason": str(exc)}
    raw_text = texts[o_name]
    lines = [_normalize(line) for line in raw_text.splitlines()]
    text = _normalize(raw_text)
    frags = _fragments(evidence)
    if not frags or any(len(fr) < MIN_FRAGMENT_LEN for fr in frags):
        return {"id": fid, "o_name": o_name, "result": "unverifiable",
                "reason": "цитата пустая или слишком короткая для механической проверки"}
    full = _normalize(evidence)
    if bounds is not None:
        lo, hi = bounds
        selected = " ".join(lines[lo - 1:hi])
        if all(fr in selected for fr in frags):
            return {"id": fid, "o_name": o_name, "result": "verified", "reason": ""}
        if all(fr in text for fr in frags):
            actual = "; ".join(
                f"фрагмент {index}: строки {_fragment_lines(fr, lines)}"
                for index, fr in enumerate(frags, 1))
            return {"id": fid, "o_name": o_name, "result": "mismatch",
                    "reason": "цитата вне заявленного диапазона; " + actual}
    elif (full and full in text) or (len(frags) > 1 and all(fr in text for fr in frags)):
        return {"id": fid, "o_name": o_name, "result": "verified",
                "reason": "расположение не проверено"}
    missing = sum(1 for fr in frags if fr not in text)
    return {"id": fid, "o_name": o_name, "result": "mismatch",
            "reason": f"цитата не найдена в указанном файле "
                      f"(не найдено фрагментов: {missing} из {len(frags)})"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Механическая сверка: цитата замечания в указанном манифестом файле")
    parser.add_argument("--findings", required=True,
                        help="JSON с замечаниями: {\"findings\": [{id, o_name, evidence}]}")
    parser.add_argument("--manifest", required=True,
                        help="JSON-манифест соответствий O-имя → файл копии")
    args = parser.parse_args()

    try:
        fdata = json.loads(Path(args.findings).read_text(encoding="utf-8"))
        mdata = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    except Exception as e:
        _emit({"status": "error", "reason": "не удалось прочитать входные JSON: " + str(e)})
        sys.exit(2)
    findings = fdata.get("findings") if isinstance(fdata, dict) else None
    if not isinstance(findings, list):
        _emit({"status": "error", "reason": "findings должен быть списком объектов"})
        sys.exit(2)
    if not isinstance(mdata, dict):
        _emit({"status": "error", "reason": "манифест должен быть объектом O-имя → файл"})
        sys.exit(2)

    manifest_dir = Path(args.manifest).parent
    texts: dict[str, str] = {}
    needed = {f.get("o_name") for f in findings
              if isinstance(f, dict) and isinstance(f.get("o_name"), str)}
    for o_name in sorted(needed):
        if o_name not in mdata:
            continue  # отсутствие в манифесте — per-замечание mismatch, не ошибка CLI
        p = Path(mdata[o_name])
        if not p.is_absolute():
            p = manifest_dir / p
        if not p.is_file():
            _emit({"status": "error",
                   "reason": "файл копии по манифесту не найден: " + mdata[o_name]})
            sys.exit(1)
        texts[o_name] = p.read_text(encoding="utf-8", errors="replace")

    results = []
    for f in findings:
        if not isinstance(f, dict):
            results.append({"id": "?", "o_name": "", "result": "unverifiable",
                            "reason": "замечание не является объектом"})
        else:
            results.append(verify_finding(f, texts))
    summary = {r: sum(1 for x in results if x["result"] == r)
               for r in ("verified", "mismatch", "unverifiable")}
    _emit({"status": "ok", "results": results, "summary": summary})


if __name__ == "__main__":
    main()

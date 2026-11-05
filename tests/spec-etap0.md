# Спецификация тестов этапа 0.2 — для субагента

Обязательный набор — `tests/README.md` (13 тестов). Здесь — точные контракты
реализованных скриптов: формы вызова, статусы, коды выхода, утверждения.
Ничего сверх этой спеки не тестировать и не менять в скриптах.

## Общие правила

- Python 3.12, pytest. Библиотеки уже установлены: python-docx, openpyxl, pypdf.
- Все данные — **синтетические** (SYNTH-*), только во временных папках
  (`tmp_path`), боевые пути не используются.
- Скрипты: `D:\expert-panel\skill\scripts\`. В тестах импортировать их как
  модули: в `tests/conftest.py` добавить
  `sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "scripts"))`.
- CLI запускать через `subprocess.run([sys.executable, str(SCRIPTS / "<имя>.py"), ...],
  capture_output=True, text=True, encoding="utf-8", env=...)`. В env добавлять
  `PYTHONUTF8=1`.
- Один тест = один кейс из README; файлы: `tests/test_extract_text.py`,
  `tests/test_scan_secrets.py`,  `tests/test_journal.py`, `tests/test_report.py`.
  Помощь (запуск CLI) — в `tests/conftest.py`.
- Фикстура готова: `tests/fixtures/secret.pdf` — PDF с текстовым слоем,
  содержит `api_key=SYNTH-KEY-XYZ-9876543210`.
- Прогон тихий: `pytest -q`. Итог — сколько прошло/упало. Фикстуры docx/xlsx
  создавать в тесте (python-docx / openpyxl).

## Контракты скриптов

### extract_text.py

CLI: `python extract_text.py <путь> [--json]` → stdout всегда ровно одна
JSON-строка: `{"status": "ok", "anchor_type": "line|para|sheet_row|page"}`
(текст никогда не выводится) — exit 0; или
`{"status": "not_extractable", "reason": "..."}` — exit 1.
Модуль: `extract_text.extract(path) -> dict` (те же поля + `"text"` внутри).

### scan_secrets.py

CLI:
- `scan_secrets.py scan --o-name O1 --path <файл>` →
  `{"status": "ok", "o_name": ..., "findings": [{"o_name", "anchor", "kind", "category"}...]}`.
  kind — `bearer|api_key|token|password|telegram_token|webhook` (category=secret)
  или `email|phone|address` (category=contact_pii). anchor — «строка N» или
  маркер «[абзац N]» и т.п. **Значений в выводе нет никогда.**
- `scan_secrets.py prepare --o-name O1 --path <файл> --mode mask|exclude
  --work-dir <dir>` → `{"status": "ok", "o_name", "copy": "<путь>"}`.
  Копия: `<work-dir>/O1.md`, utf-8. mask: секрет → `[СЕКРЕТ:вид]`,
  контакты → `[EMAIL]` / `[ТЕЛЕФОН]` / `[АДРЕС]`. exclude: строка с секретом →
  `[УЧАСТОК ИСКЛЮЧЁН — не проверялся]`, контакты всё равно замаскированы.
- Неизвлекаемый файл → `{"status": "not_extractable", "note": "не проверено на
  секреты", "reason": ...}` exit 1.

### journal.py

CLI: **`--root <dir>` ставится ДО подкоманды**:
`journal.py --root <dir> <sub> ...` — изолированный корень для тестов.

- `lock [--run-id R] [--pid N] [--confirm-stale]` →
  `{"status": "locked", "run_id", "pid"}`; занято живым →
  `{"status": "refused", ...}` **exit 2**; lock мёртвого pid без
  `--confirm-stale` → `{"status": "stale_lock", ...}` **exit 2**; с флагом —
  lock пересоздан.
- `unlock [--run-id R]` → `{"status": "unlocked"|"no_lock"}`.
- `append --run-id R --event-id E --type T [--data JSON]` →
  `{"status": "ok", "seq": N}`; дубль event_id →
  `{"status": "duplicate_event_id"}` **exit 3**; неизвестный тип — exit 2.
  Типы (ТЗ §10): run_started, preflight_shown, preflight_approved,
  finding_detected, phase_experts_started, expert_finished, checkpoint_passed,
  judge_finished, report_saved, risk_accepted_by_user, retention_cleanup_proposed,
  report_deleted, run_finished, run_stopped, journal_repaired.
- `list` → `{"status": "ok", "events": [{"seq","run_id","type"}...]}`.
- `check` → `{"status": "ok", "events": N}` exit 0; проблемы →
  `{"status": "invalid", "events", "problems": [...]}` **exit 4**.
  Проблемы: повреждённые строки, непрерывность seq (1..N), уникальность
  event_id, у каждого run_id есть run_started (кроме journal_repaired),
  каждый перенос в quarantine закрыт событием с тем же repair_id.
- `repair [--confirm]` → без флага `{"status": "confirm_required"}` exit 2;
  с флагом: перенос повреждённых строк в `<root>/history/history.quarantine`
  (JSONL: заголовок `{"type":"quarantine_header","repair_id","utc_ts","seq","reason"}`
  + строки `{"type":"quarantine_line","repair_id","raw"}`) + событие
  `journal_repaired` с тем же repair_id (data.repair_id) →
  `{"status": "repaired", "repair_id", "moved_lines"}`. Если quarantine уже
  содержит заголовок с repair_id без закрывающего события (незакрытый перенос) —
  quarantine НЕ трогается, дописывается только событие. Нечего делать →
  `{"status": "nothing_to_do"}` exit 0.
- `remains [--confirm-delete]` → `{"status": "clean"}` | `{"status": "found",
  "dirs": [...]}` (без флага ничего не удаляет) | `{"status": "deleted", "dirs"}`.

Формат строки журнала: `{"seq", "run_id", "event_id", "type", "utc_ts", "data"}`,
по одной полной строке на событие. run.lock: JSON `{"pid", "run_id", "utc_ts"}`.

### report.py

CLI: `report.py --input verdict.json --out-dir <dir> [--retention-days N]`.
Env `EXPERT_PANEL_RETENTION_DAYS`: **пустая строка = дефолт 90**.
→ `{"status": "ok", "md", "json"}`; схема неверна →
`{"status": "invalid_schema"}` exit 2.
Выход: `<run_id>.md` + `<run_id>.json`; post-mask секретов и контактов по всем
строкам; `retention_until` = дата (сегодня + retention_days) ISO, если не задана.
Модуль: `report.build(verdict_data, out_dir, retention_days=90)`.

Минимальный валидный verdict (для фикстуры в тесте):

```json
{"run_id": "t-run-1", "object": {"type": "резюме",
  "materials": [{"o_name": "O1", "format": "md", "size": "1 КБ"}]},
 "goal": "тест", "preflight_summary": {"experts": [], "models": [], "depth": "тест"},
 "findings": [{"id": "F-1", "priority": "Важно", "type": "подтверждённая",
   "location": "O1, [абзац 1]", "evidence": "...", "problem": "...",
   "consequence": "...", "recommendation": "...", "confidence": "высокая"}],
 "verdict": "Принято с замечаниями", "scores": {"критерий": 3},
 "checked_areas": ["x"], "unchecked_areas": [], "limitations": [],
 "recommendations": [], "token_stats": {"input": "1k", "note": "оценка"}}
```

### check_numbers.py / compare_reports.py

В 13 обязательных тестах не участвуют (смoke уже пройден КЛОДИ).

## 13 тестов — точные утверждения

1. **Секрет в docx/xlsx/pdf обнаруживается.** docx (python-docx, параграф
   `api_key=SYNTH-KEY-ABC-777`), xlsx (openpyxl, ячейка `password=SYNTH-PASS-55`),
   `tests/fixtures/secret.pdf`. Для каждого: `scan --o-name O1 --path …` →
   status ok, findings непустые, kind = api_key/password, category = secret,
   значение (`SYNTH-KEY`, `SYNTH-PASS`) не встречается в stdout и stderr.
2. **PDF без текстового слоя → «не проверено на секреты».** Создать пустой PDF:
   `from pypdf import PdfWriter; w = PdfWriter(); w.add_blank_page(612, 792);
   w.write(tmp/"blank.pdf")`. CLI scan → exit 1, status not_extractable,
   note «не проверено на секреты». Проверить и extract_text CLI: exit 1,
   status not_extractable.
3. **Тишина сканера.** md с `Bearer SYNTH-BEARER-TOKEN-42`,
   `token=SYNTH-TOKEN-42`, email `synth@example.com`, телефон `+7 912 345 67 89`,
   адрес `ул. Синтетическая, д. 7`. CLI scan (capture_output) → assert: ни одно
   из значений (`SYNTH-BEARER`, `SYNTH-TOKEN`, `synth@example.com`, `912`,
   `Синтетическая`) не в stdout и не в stderr; findings содержат все 4+
   категории; каждая находка — только o_name/anchor/kind/category.
4. **Контакты замаскированы в копии.** Тот же md → prepare --mode mask → в
   файле `<work>/O1.md` есть `[EMAIL]`, `[ТЕЛЕФОН]`, `[АДРЕС]`; нет
   `synth@example.com`, `912 345`, `Синтетическая`. Секрет → `[СЕКРЕТ:api_key]`-подобная маска.
5. **Пост-маска в отчёте.** verdict JSON (выше), но evidence содержит
   `почта synth@example.com`, problem содержит `password=SYNTH-PASS-77`.
   build → в обоих файлах (md и json): `[EMAIL]` и `[СЕКРЕТ:password]`
   присутствуют, `synth@example.com` и `SYNTH-PASS` — отсутствуют.
6. **До prepare в work нет файлов.** md с секретом → scan CLI → в
   `work/<run-id>/` файлов нет (папки нет или пуста); prepare → ровно один
   файл `O1.md`.
7. **Пустой env → дефолты.** `env["EXPERT_PANEL_RETENTION_DAYS"] = ""` →
   build → в json `retention_until` = (дата сегодня + 90 дней).isoformat().
   (Сравнивать только дату, не время.)
8. **Двойной запуск → отказ.** `lock --run-id r1 --pid <os.getpid()>` → locked;
   повторный `lock --run-id r2` → exit 2, status refused.
9. **Lock мёртвого pid → снятие по подтверждению.** Взять pid закончившегося
   процесса: `p = subprocess.Popen(["cmd", "/c", "exit"]); p.wait()` → pid мёртв.
   `lock --run-id r1 --pid p.pid` → status stale_lock, exit 2; без флага lock
   не пересоздан (файл прежний). С `--confirm-stale` → locked, run_id = r1.
10. **Остатки work.** mkdir `<root>/work/a1`, `a2` → `remains` → found,
    dirs=[a1,a2], папки живы; `remains --confirm-delete` → deleted, папок нет.
11. **Повреждённый хвост → repair.** append run_started + preflight_shown
    (run-id r1, event e1/e2) → check ok. Портим: дописать в history.jsonl
    без \n обрывок `{"seq":3,"run_id":"r1"`. check → exit 4. repair без
    --confirm → exit 2. repair --confirm → repaired. Снова: check ok;
    в quarantine заголовок с repair_id R; в журнале событие journal_repaired
    с data.repair_id == R; append нового события → seq == 4 (макс. валидный 3 + 1).
12. **Незакрытый перенос → только запись события.** Журнал с run_started
    (r1, e1). Вручную дописать в history.quarantine строку
    `{"type": "quarantine_header", "repair_id": "R-SPEC-12", "utc_ts": "x",
    "seq": 1, "reason": "тест"}`. `check` → exit 4 (перенос не закрыт).
    Посчитать строки quarantine до. `repair --confirm` → repaired,
    moved_lines == 0; quarantine не вырос (столько же строк); в журнале
    добавилось ровно одно событие journal_repaired с repair_id R-SPEC-12;
    `check` → ok.
13. **Дубль event_id → ошибка.** append e1 → ok; повторно append с тем же
    --event-id e1 → exit 3, status duplicate_event_id; в журнале по-прежнему
    одно событие (list); check ok.

## Отчёт субагента

Прогон `pytest -q` в `D:\expert-panel`. Итог: сколько тестов написано,
сколько прошло. Упавший тест — не чинить молча: если несовпадение со спекой —
исправить тест; если подозрение на баг скрипта — не менять скрипт, записать
факт в отчёт.

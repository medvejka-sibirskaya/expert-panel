# Сверка §14 ТЗ v1.3 по документации Claude Code

**Дата:** 04.11.2026 · **Метод:** поиск по актуальной документации Claude Code (code.claude.com недоступен для прямого чтения из среды Медвежки — сетевые ограничения; факты собраны через поиск по официальным страницам docs) · **Принцип:** короткая сверка по существу, без генерации новых требований

## Результаты

| Пункт §14 | Вердикт | Что подтверждено | Источник |
|---|---|---|---|
| Независимость субагентов | **Подтверждено** | Каждый не-fork субагент стартует со свежим изолированным контекстом: без истории родительского диалога, без его результатов и системного промпта — только свой промпт, делегация, CLAUDE.md, git-статус. Назад возвращается только финальный отчёт | [Sub-agents docs](https://code.claude.com/docs/en/sub-agents), [SDK subagents](https://code.claude.com/docs/en/agent-sdk/subagents) |
| Ограничение доступа экспертов | **Подтверждено, лучше заложенного** | `tools` во frontmatter — allowlist: `tools: Read, Grep, Glob` = строго read-only (Write/Edit запрещены). Дополнительно есть `disallowedTools` (denylist). Запрета конкретных путей на уровне агента нет — fallback из ТЗ (инструкция в брифе + read-only инструменты) остаётся как есть | [Sub-agents docs](https://code.claude.com/docs/en/sub-agents) |
| Параллельность волны | **Подтверждено** | Несколько субагентов в одном запросе работают параллельно; лимит одновременных — 20 по умолчанию (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`). Нашей волне из 4–5 экспертов — с большим запасом | [Run agents in parallel](https://code.claude.com/docs/en/agents), [claude.com article](https://claude.com/resources/articles/subagents-in-claude-code) |
| Закрепление моделей через frontmatter | **Подтверждено, с одной деталью ниже** | Поле `model` во frontmatter: алиасы (`sonnet`, `opus`, `haiku`, `fable`), полный ID модели или `inherit`. Порядок выбора: model в вызове Agent → frontmatter → env `CLAUDE_CODE_SUBAGENT_MODEL` → модель сессии | [Sub-agents docs](https://code.claude.com/docs/en/sub-agents) |
| Токены по субагентам | **Как и заложено в ТЗ** | Простого per-agent счётчика в диалоге нет; транскрипты субагентов хранятся отдельно с метаданными, просмотр — через `/tasks`. Подход ТЗ (оценка диапазоном с пометкой «оценка») — корректный | [Sub-agents docs](https://code.claude.com/docs/en/sub-agents) |
| Запуск Python из скилла | **Подтверждено** | Канонический паттерн: скрипты в папке скилла (`scripts/`), вызов через Bash/PowerShell: `python ${CLAUDE_SKILL_DIR}/scripts/...`; пред-одобрение — `allowed-tools` во frontmatter. Таймаут по умолчанию 2 минуты — для наших скриптов достаточно | [Skills docs](https://code.claude.com/docs/en/skills) |
| Расположение скилла и агентов | **Подтверждено** | Личные скиллы — `~/.claude/skills/`, имя файла строго `SKILL.md`, папка kebab-case («expert-panel» — корректно). Агенты — `.claude/agents/*.md` | [Skills docs](https://code.claude.com/docs/en/skills), [Sub-agents docs](https://code.claude.com/docs/en/sub-agents) |
| Read для PDF | **Снято архитектурно** | В v1.3 эксперты PDF напрямую не читают — только разрешённые md-копии. Проверка не требуется | — |

## Две детали для реализации (не требования, фиксация)

1. **Алиасы vs идентификаторы шлюза.** Frontmatter принимает алиасы Claude Code (`sonnet`, `opus`, `haiku`, `fable`), а не имена моделей шлюза (`glm-5.3:cloud` и т.п.). В среде Медвежки шлюз сам мапит алиасы на GLM-модели; какой алиас соответствует `glm-5.3:cloud` / `glm-5.3-flash:cloud` — проверяется живым тестом на этапе фактической проверки среды (запуск микро-субагента на каждом алиасе), не документацией. Параметр `model` в вызове Agent принимает только алиасы — это же ограничение учитываем при назначении моделей в Preflight.
2. **Env-переменная `CLAUDE_CODE_SUBAGENT_MODEL`.** Может перебить frontmatter агентов. При настройке убедиться, что она не задана (иначе состав моделей в Preflight не будет соответствовать факту).

## Итог

Невыполнимых пунктов в ТЗ v1.3 нет. Один fallback остаётся предусмотренным (запрет путей — инструкцией в брифе), один вопрос перенесён на живой тест (маппинг алиасов шлюза на GLM-модели). ТЗ не требует изменений по результатам сверки.

**Источники:** [Create custom subagents](https://code.claude.com/docs/en/sub-agents) · [Run agents in parallel](https://code.claude.com/docs/en/agents) · [Subagents in the SDK](https://code.claude.com/docs/en/agent-sdk/subagents) · [Extend Claude with skills](https://code.claude.com/docs/en/skills) · [How and when to use subagents](https://claude.com/resources/articles/subagents-in-claude-code) · [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
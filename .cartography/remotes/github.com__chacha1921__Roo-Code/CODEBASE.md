# CODEBASE

## AI Consumption Guide
- Architecture Overview uses graph-level counts plus Surveyor architectural hub and SCC metadata when available.
- Critical Path is driven by architectural_hubs/PageRank from Surveyor-enriched module graph attributes.
- Data Sources & Sinks are derived from merged lineage dataset nodes and edge metadata from Python, SQL, and config analysis.
- Module Purpose Index is grounded in Semanticist purpose_statement and domain_cluster node attributes.
- Lineage merge logic: networkx.compose with dialect postgres.
- Onboarding citations flow from day_one_answers into onboarding_brief via preserved source_file/line_range evidence.

## Architecture Overview
The codebase contains 0 modules, 11 datasets, and 7 transformations connected by 16 graph edges. Its structure is centered around 0 high-importance architectural hubs, with 0 circular dependency clusters currently visible, which suggests the main operational shape, dependency pressure, and likely refactor hotspots for future work.

## Critical Path
- No module import data available.

## Data Sources & Sinks
### Sources
- runs
- tasks
- toolErrors
- tasks_run_id_runs_id_fk
- tasks_task_metrics_id_taskMetrics_id_fk
- toolErrors_run_id_runs_id_fk
- toolErrors_task_id_tasks_id_fk
- public.runs
- public.taskMetrics
- public.tasks
- tasks_language_exercise_idx

### Sinks
- No sink nodes identified.

## Known Debt
- No circular dependencies or documentation drift flags found.

## High-Velocity Files
- src/shared/tools.ts (7 changes / 30d)
- src/core/assistant-message/presentAssistantMessage.ts (7 changes / 30d)
- src/core/webview/ClineProvider.ts (7 changes / 30d)
- src/api/providers/anthropic.ts (7 changes / 30d)
- src/core/task/Task.ts (7 changes / 30d)

## Module Purpose Index
- No module purpose statements available.
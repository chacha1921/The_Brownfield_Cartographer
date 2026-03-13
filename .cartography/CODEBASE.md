# CODEBASE

## Architecture Overview
The codebase contains 20 modules, 0 datasets, and 0 transformations connected by 117 graph edges. Its structure is centered around 20 high-importance architectural hubs, with 0 circular dependency clusters currently visible, which suggests the main operational shape, dependency pressure, and likely refactor hotspots for future work.

## Critical Path
- src/models/schemas.py (PageRank=0.2346)
- src/graph/knowledge_graph.py (PageRank=0.1129)
- src/orchestrator.py (PageRank=0.0868)
- src/analyzers/sql_lineage.py (PageRank=0.0587)
- src/cli.py (PageRank=0.0469)

## Data Sources & Sinks
### Sources
- No dataset lineage sources identified in the current repository scan.

### Sinks
- No dataset lineage sinks identified in the current repository scan.

## Known Debt
- No circular dependencies or documentation drift flags found.

## High-Velocity Files
- pyproject.toml (5 changes / 30d)
- src/agents/hydrologist.py (5 changes / 30d)
- src/analyzers/__init__.py (5 changes / 30d)
- src/brownfield_cartographer/cli.py (5 changes / 30d)
- README.md (4 changes / 30d)
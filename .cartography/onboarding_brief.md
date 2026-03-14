# onboarding_brief

This brief summarizes the semantic synthesis for a new forward-deployed engineer joining the codebase.
Citations below are propagated directly from Semanticist day-one answers to keep downstream references stable for AI-assisted onboarding.

## What business capability does this codebase primarily support?
This codebase primarily supports **software intelligence**, offering capabilities to analyze brownfield systems and generate comprehensive architectural and semantic insights. It maps module dependencies, traces data lineage across various assets, and enriches these findings with semantic understanding for improved codebase comprehension.

Evidence:
- README.md:L1-L30 via llm-inference
- src/agents/semanticist.py:L1-L30 via llm-inference
- src/orchestrator.py:L1-L30 via llm-inference

## Which modules and workflows should a new engineer read first to understand the system's critical path?
To grasp the system's critical path, a new engineer should first examine `src/cli.py` as the command-line entry point, which then delegates to `src/orchestrator.py`. The `Orchestrator` module is central, coordinating all analysis agents and managing the entire workflow. Understanding `src/graph/knowledge_graph.py` is crucial for comprehending how all discovered architectural data is structured and persisted. Finally, `src/models/schemas.py` defines the fundamental node and edge types that form the basis of the knowledge graph, making it essential for data interpretation.

Evidence:
- src/cli.py:L1-L30 via llm-inference
- src/orchestrator.py:L1-L30 via llm-inference
- src/orchestrator.py:L26-L55 via llm-inference
- src/graph/knowledge_graph.py:L1-L30 via llm-inference
- src/models/schemas.py:L76-L85 via llm-inference

## Where are the highest-risk change surfaces, and why?
The highest-risk change surfaces are concentrated in modules with high architectural centrality or frequent modification. `src/models/schemas.py` is particularly sensitive due to its high PageRank (0.21), as it defines the core data models for all graph entities, meaning changes here propagate widely. `src/orchestrator.py` also presents a significant risk, exhibiting both high PageRank (0.05) and a high change velocity (5 changes in 30 days), indicating it's a frequently modified central component. Additionally, `src/graph/knowledge_graph.py` is an architectural hub (PageRank: 0.10) responsible for graph management, making it a critical point for system stability.

Evidence:
- src/models/schemas.py:L1-L30 via llm-inference
- src/orchestrator.py:L1-L30 via llm-inference
- src/orchestrator.py:L1-L30 via llm-inference
- src/graph/knowledge_graph.py:L1-L30 via llm-inference
- src/orchestrator.py:L1-L30 via llm-inference

## How does data enter, move through, and exit the system?
Data enters the system through static analysis of source code files, including Python scripts, SQL queries, and YAML configuration files (dbt, Airflow). The `HydrologistAgent` coordinates this ingestion, utilizing specialized analyzers like `PythonDataFlowAnalyzer`, `SQLLineageAnalyzer`, and `DAGConfigAnalyzer` to extract lineage information. This extracted data, representing datasets and transformations, is then integrated into a `KnowledgeGraph` instance. The system concludes by persisting this comprehensive data flow map as `lineage_graph.json` within the `.cartography/` output directory.

Evidence:
- src/agents/hydrologist.py:L1-L30 via llm-inference
- src/agents/hydrologist.py:L26-L55 via llm-inference
- src/analyzers/python_data_flow.py:L51-L80 via llm-inference
- src/analyzers/sql_lineage.py:L101-L130 via llm-inference
- src/analyzers/dag_config_parser.py:L26-L55 via llm-inference
- src/orchestrator.py:L76-L105 via llm-inference

## What domain architecture map best explains how responsibilities are split across the codebase?
The codebase's responsibilities are effectively segmented into distinct domain clusters. The **orchestration** cluster, exemplified by `src/orchestrator.py` and `src/cli.py`, manages the overall analysis execution and user interface. **Software intelligence** agents, such as `src/agents/semanticist.py`, `src/agents/surveyor.py`, and `src/agents/hydrologist.py`, perform the core analytical tasks of extracting structural, semantic, and data lineage insights. The **data lineage** cluster, comprising modules like `src/analyzers/sql_lineage.py` and `src/analyzers/python_data_flow.py`, provides the specific static analysis capabilities. Underlying these are the **data model** (`src/models/schemas.py`) and **knowledge graph** (`src/graph/knowledge_graph.py`) clusters, which establish the fundamental data structures and the persistent graph representation used throughout the system.

Evidence:
- src/orchestrator.py:L1-L30 via llm-inference
- src/cli.py:L1-L30 via llm-inference
- src/agents/semanticist.py:L1-L30 via llm-inference
- src/analyzers/sql_lineage.py:L1-L30 via llm-inference
- src/models/schemas.py:L1-L30 via llm-inference
- src/graph/knowledge_graph.py:L1-L30 via llm-inference

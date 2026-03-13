# onboarding_brief

This brief summarizes the semantic synthesis for a new forward-deployed engineer joining the codebase.

## What business capability does this codebase primarily support?
This codebase primarily supports the automated analysis of existing software repositories to generate architectural insights, data lineage maps, and semantic documentation. It aims to accelerate understanding and onboarding for engineers by synthesizing complex system information into structured knowledge graphs and human-readable reports, such as the `onboarding_brief.md` and `day_one_answers.json`.

Evidence:
- README.md:L1-L30 via llm-inference
- src/orchestrator.py:L76-L105 via llm-inference
- src/agents/semanticist.py:L276-L305 via llm-inference
- src/agents/hydrologist.py:L1-L30 via llm-inference

## Which modules and workflows should a new engineer read first to understand the system's critical path?
To grasp the system's critical path, a new engineer should begin with `src/cli.py`, which serves as the primary user interface for initiating repository analysis. Next, examine `src/orchestrator.py` to understand how the various analysis agents are coordinated and how incremental updates are managed. Then, review `src/models/schemas.py` to familiarize yourself with the fundamental data structures like `ModuleNode`, `DatasetNode`, and `EdgeType` that represent the system's knowledge. Finally, explore `src/graph/knowledge_graph.py` to see how these schemas are instantiated and managed within the central graph data store.

Evidence:
- src/cli.py:L1-L30 via llm-inference
- src/cli.py:L76-L105 via llm-inference
- src/orchestrator.py:L51-L80 via llm-inference
- src/models/schemas.py:L76-L85 via llm-inference
- src/graph/knowledge_graph.py:L1-L30 via llm-inference

## Where are the highest-risk change surfaces, and why?
The highest-risk change surfaces include `src/models/schemas.py`, which defines the foundational data models for all graph entities; modifications here would propagate across the entire system due to its architectural centrality. Similarly, `src/graph/knowledge_graph.py` presents a significant risk, as it encapsulates the core graph storage and manipulation logic. Changes to `src/orchestrator.py` are also high-risk because it coordinates all analysis phases, making it central to the system's operational flow. Lastly, `src/analyzers/sql_lineage.py` is a high-velocity core file critical for data lineage extraction, meaning frequent changes could introduce regressions in a key analysis capability.

Evidence:
- src/models/schemas.py:L1-L30 via llm-inference
- src/graph/knowledge_graph.py:L1-L30 via llm-inference
- src/orchestrator.py:L26-L55 via llm-inference
- src/analyzers/sql_lineage.py:L76-L105 via llm-inference

## How does data enter, move through, and exit the system?
Data enters the system via a specified repository path, which can be a local directory or a remote Git URL, handled by `src/cli.py`. The `Orchestrator` then coordinates the analysis: `SurveyorAgent` processes source code to build a module import graph and extract change velocity, while `HydrologistAgent` analyzes Python, SQL, dbt, and Airflow configurations to construct a data lineage graph. Finally, `SemanticistAgent` enriches these graphs with LLM-generated purpose statements and domain clusters, synthesizing the information into human-readable outputs. The system exits by persisting these insights as JSON graph files (`module_graph.json`, `lineage_graph.json`), a comprehensive `CODEBASE.md` report, an `onboarding_brief.md`, and `day_one_answers.json` within the `.cartography/` directory of the analyzed repository.

Evidence:
- src/cli.py:L1-L30 via llm-inference
- src/orchestrator.py:L1-L30 via llm-inference
- src/orchestrator.py:L76-L105 via llm-inference
- src/orchestrator.py:L76-L105 via llm-inference
- src/orchestrator.py:L76-L105 via llm-inference

## What domain architecture map best explains how responsibilities are split across the codebase?
The codebase's responsibilities are clearly delineated into several domain clusters. The `orchestration` cluster manages the overall analysis workflow, including CLI interactions and output persistence. `dependency analysis` encompasses the static code analysis tools for extracting module imports, data flow, and parsing configuration files like dbt and Airflow. The `system model` cluster defines the core data structures, such as `Node` and `EdgeType`, used to represent architectural entities. All analyzed information is stored and managed by the `knowledge graph` cluster. Finally, the `software intelligence` cluster is responsible for semantic enrichment, domain clustering, and synthesizing human-readable insights, including the day-one onboarding answers.

Evidence:
- src/cli.py:L1-L30 via llm-inference
- src/orchestrator.py:L26-L55 via llm-inference
- src/analyzers/sql_lineage.py:L76-L105 via llm-inference
- src/models/schemas.py:L1-L30 via llm-inference
- src/agents/semanticist.py:L276-L305 via llm-inference

# onboarding_brief

This brief summarizes the semantic synthesis for a new forward-deployed engineer joining the codebase.

## What business capability does this codebase primarily support?
This codebase primarily supports the automated analysis of existing software repositories to generate architectural insights and comprehensive onboarding documentation. It extracts module dependencies, data lineage, and semantically enriches these findings to produce structured reports and answers for new engineers.

Evidence:
- README.md:L1-L30 via llm-inference
- pyproject.toml:L1-L30 via llm-inference
- src/orchestrator.py:L51-L80 via llm-inference
- src/agents/semanticist.py:L276-L305 via llm-inference

## Which modules and workflows should a new engineer read first to understand the system's critical path?
To grasp the system's critical path, a new engineer should begin with `src/cli.py` to see how user commands initiate analysis and handle repository acquisition. Next, examine `src/orchestrator.py`, which coordinates the entire process from graph construction by agents like `SurveyorAgent` and `HydrologistAgent` to semantic enrichment and artifact generation. Understanding `src/graph/knowledge_graph.py` is crucial as it defines the central data structure for all architectural insights, while `src/models/schemas.py` outlines the fundamental node and edge types that populate these graphs.

Evidence:
- src/cli.py:L51-L80 via llm-inference
- src/orchestrator.py:L51-L80 via llm-inference
- src/graph/knowledge_graph.py:L1-L30 via llm-inference
- src/models/schemas.py:L1-L30 via llm-inference

## Where are the highest-risk change surfaces, and why?
The highest-risk change surfaces include `src/models/schemas.py` due to its architectural centrality (highest PageRank) in defining core data models like `Node` and `EdgeType`, making any modification ripple across the entire system. `src/graph/knowledge_graph.py` is also critical, holding the second-highest PageRank, as it manages the fundamental graph operations. Additionally, `src/cli.py` and `src/agents/hydrologist.py` exhibit high change velocity, indicating frequent modifications that could introduce instability at the user interface or within the complex data lineage analysis logic, respectively.

Evidence:
- src/models/schemas.py:L1-L30 via llm-inference
- src/graph/knowledge_graph.py:L1-L30 via llm-inference
- src/cli.py:L51-L80 via llm-inference
- src/agents/hydrologist.py:L1-L30 via llm-inference

## How does data enter, move through, and exit the system?
Data enters the system through a user-specified repository path, which can be a local directory or a remote GitHub URL, handled by `src/cli.py`'s `resolve_repo_path` function. It then moves through processing stages orchestrated by `src/orchestrator.py`: `SurveyorAgent` builds a module graph from Python files, `HydrologistAgent` constructs a data lineage graph by analyzing Python data flow, SQL, and YAML configurations, and `SemanticistAgent` enriches these graphs with LLM-generated insights. Finally, processed data exits as persistent artifacts in the `.cartography/` directory, including `module_graph.json`, `lineage_graph.json`, `CODEBASE.md`, `onboarding_brief.md`, and `day_one_answers.json`.

Evidence:
- src/cli.py:L26-L55 via llm-inference
- src/orchestrator.py:L76-L105 via llm-inference
- src/agents/hydrologist.py:L1-L30 via llm-inference
- src/orchestrator.py:L101-L130 via llm-inference
- README.md:L51-L80 via llm-inference

## What domain architecture map best explains how responsibilities are split across the codebase?
The codebase's responsibilities are clearly delineated across several domain clusters. The 'orchestration' cluster, exemplified by `src/orchestrator.py` and `src/cli.py`, manages the overall workflow and user interaction. 'Data lineage' components, such as `src/analyzers/sql_lineage.py` and `src/agents/hydrologist.py`, focus on static analysis to map data dependencies. The 'knowledge graph' domain, including `src/graph/knowledge_graph.py` and `src/models/schemas.py`, provides the foundational data structures. Lastly, 'software intelligence' modules like `src/agents/semanticist.py` are responsible for semantic enrichment and documentation synthesis using large language models.

Evidence:
- src/orchestrator.py:L26-L55 via llm-inference
- src/cli.py:L1-L30 via llm-inference
- src/analyzers/sql_lineage.py:L76-L105 via llm-inference
- src/graph/knowledge_graph.py:L1-L30 via llm-inference
- src/agents/semanticist.py:L276-L305 via llm-inference

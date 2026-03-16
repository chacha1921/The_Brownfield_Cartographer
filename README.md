# Brownfield Cartographer

Brownfield Cartographer analyzes an existing codebase and produces JSON graph artifacts for:

- module-level import relationships
- data-lineage relationships across Python pipelines, SQL, dbt, and Airflow assets
- semantic enrichment for module purpose, domain clustering, and day-one onboarding synthesis

The tool writes its outputs into a `.cartography/` directory inside the analyzed repository.

## Requirements

- Python 3.10+
- `uv`
- `git` available on your `PATH`

## Install with uv

From the project root:

```bash
uv sync
```

This creates or updates the local virtual environment and installs all project dependencies from `pyproject.toml`.

## CLI usage

The main analyze command is:

```bash
uv run brownfield-cartographer analyze --repo-path <path-or-url>
```

Helpful flags:

```bash
uv run brownfield-cartographer analyze --repo-path <path-or-url> --force-full --sql-dialect spark
```

- `--force-full` skips cached graph reuse and runs a clean full analysis.
- `--sql-dialect` selects the SQLGlot dialect used for SQL parsing. The default remains `postgres`, so existing flows keep working unchanged.

You can also still use the backward-compatible form without the subcommand:

```bash
uv run brownfield-cartographer --repo-path <path-or-url>
```

To inspect existing artifacts with Navigator, use:

```bash
uv run brownfield-cartographer query --repo-path <local-repo-path>
```

Or ask a one-shot question:

```bash
uv run brownfield-cartographer query --repo-path <local-repo-path> --question "blast radius for src/pipeline.py"
```

To generate a presentation-friendly HTML dashboard from existing artifacts, use:

```bash
uv run brownfield-cartographer dashboard --repo-path <repo-path-or-remote-url>
```

You can also point directly at a persisted artifact directory, or choose an explicit HTML output path:

```bash
uv run brownfield-cartographer dashboard --repo-path .cartography/remotes/github.com__mitodl__ol-data-platform --output tmp/mitodl-dashboard.html
```

## Analyze a local repository

Example using a local directory path:

```bash
uv run brownfield-cartographer analyze --repo-path .
```

Or point at any other local repository:

```bash
uv run brownfield-cartographer analyze --repo-path /path/to/repository
```

## Analyze a GitHub repository

If `--repo-path` starts with `http`, `https`, or `github.com/`, the CLI temporarily clones the repository into `/tmp` before running analysis.

Examples:

```bash
uv run brownfield-cartographer analyze --repo-path https://github.com/octocat/Hello-World
```

```bash
uv run brownfield-cartographer analyze --repo-path github.com/octocat/Hello-World
```

## Output files

After a successful run, Brownfield Cartographer writes:

- `.cartography/module_graph.json`
- `.cartography/lineage_graph.json`
- `.cartography/CODEBASE.md`
- `.cartography/onboarding_brief.md`
- `.cartography/day_one_answers.json`
- `.cartography/cartography_trace.jsonl`
- `.cartography/run_metadata.json`
- Semanticist-enriched module metadata inside `module_graph.json`

These files are created in the analyzed repository.

For remote GitHub analysis, persisted outputs are copied into `.cartography/remotes/<repo-slug>/` in the invoking workspace.

The `dashboard` command reads those existing outputs and creates a self-contained `dashboard.html` file next to the artifacts by default.

## What gets analyzed

- Python imports and module relationships
- Python data reads, writes, and SQL execution paths
- SQL lineage and write targets with per-edge metadata: `transformation_type`, `source_file`, `line_start`, `line_end`, and `dialect`
- dbt schema metadata and dependencies
- Airflow DAG task topology
- LLM-generated module purpose statements
- Domain clusters derived from semantic embeddings
- Five evidence-backed day-one onboarding answers

## Merged graph logic

`CODEBASE.md` and Navigator queries use a merged in-memory graph composed from `module_graph.json` and `lineage_graph.json`.

- Surveyor contributes module nodes, import edges, PageRank hubs, SCCs, and high-velocity metadata.
- Hydrologist contributes dataset/transformation nodes, Python/SQL/config lineage edges, SQL dialect metadata, and unresolved dynamic reference summaries.
- Semanticist contributes `purpose_statement`, `domain_cluster`, `documentation_drift`, and day-one answer citations.
- `onboarding_brief.md` preserves the same citation paths and line ranges produced in `day_one_answers.json`.

This keeps module architecture and data lineage queryable together without changing the stored source artifacts.

## Semanticist configuration

Phase 3 uses Gemini and local Ollama together:

- Gemini handles fast summarization and embeddings
- Ollama handles heavier synthesis for day-one answers

Copy the example configuration if needed:

```bash
cp .env.example .env
```

Then set at least:

- `GEMINI_API_KEY`
- `OLLAMA_BASE_URL` if your Ollama server is not running on the default `http://localhost:11434`

Default model routing in `.env` is:

- `SEMANTICIST_FAST_PROVIDER=gemini`
- `SEMANTICIST_FAST_MODEL=gemini-2.5-flash`
- `SEMANTICIST_HEAVY_PROVIDER=ollama`
- `SEMANTICIST_HEAVY_MODEL=llama3.2:latest`
- `SEMANTICIST_EMBEDDING_PROVIDER=gemini`
- `SEMANTICIST_EMBEDDING_MODEL=gemini-embedding-001`

To use the local Ollama model, make sure it is available before running analysis, for example:

```bash
ollama pull llama3.2:latest
```

If you want a different Gemini or Ollama model, update the related `.env` values without changing application code.

## Trace logging

Every Archivist action appends a record to `.cartography/cartography_trace.jsonl` with:

- `timestamp`
- `action`
- `confidence`
- `evidence`
- `analysis_methods`
- `evidence_sources`

This trace is preserved even if a later stage fails, because graph and day-one intermediate artifacts are written defensively during the run.

## Dashboard features

The generated HTML dashboard is designed for demos and quick inspection of prior runs. It includes:

- sidebar switching between Surveyor, Hydrologist, Semanticist, Archivist, and Navigator views
- node count, edge count, dominant node type, and most-connected-node metrics per view
- searchable graph nodes
- click-to-inspect node metadata
- pan and zoom controls for graph exploration
- Hydrologist source/sink hints so initial lineage sources and terminal sinks stand out visually
- built-in viewers for `CODEBASE.md`, `onboarding_brief.md`, `day_one_answers.json`, trace logs, and raw graph JSON

## Notes

- Remote repositories are cloned into a temporary directory under `/tmp` for the duration of the run.
- The analyzed repository must be cloneable with your local `git` configuration.
- If a repository has no SQL or dbt assets, `.cartography/lineage_graph.json` may be empty.
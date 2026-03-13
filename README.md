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

The main command is:

```bash
uv run brownfield-cartographer analyze --repo-path <path-or-url>
```

You can also still use the backward-compatible form without the subcommand:

```bash
uv run brownfield-cartographer --repo-path <path-or-url>
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
- Semanticist-enriched module metadata inside the generated graph payloads when Phase 3 runs

These files are created in the analyzed repository.

## What gets analyzed

- Python imports and module relationships
- Python data reads, writes, and SQL execution paths
- SQL lineage and write targets
- dbt schema metadata and dependencies
- Airflow DAG task topology
- LLM-generated module purpose statements
- Domain clusters derived from semantic embeddings
- Five evidence-backed day-one onboarding answers

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
- `SEMANTICIST_FAST_MODEL=gemini-1.5-flash`
- `SEMANTICIST_HEAVY_PROVIDER=ollama`
- `SEMANTICIST_HEAVY_MODEL=llama3.1:8b-instruct`
- `SEMANTICIST_EMBEDDING_PROVIDER=gemini`
- `SEMANTICIST_EMBEDDING_MODEL=text-embedding-004`

To use the local Ollama model, make sure it is available before running analysis, for example:

```bash
ollama pull llama3.1:8b-instruct
```

If you want a different Gemini or Ollama model, update the related `.env` values without changing application code.

## Notes

- Remote repositories are cloned into a temporary directory under `/tmp` for the duration of the run.
- The analyzed repository must be cloneable with your local `git` configuration.
- If a repository has no SQL or dbt assets, `.cartography/lineage_graph.json` may be empty.
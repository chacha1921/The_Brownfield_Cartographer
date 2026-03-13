# Brownfield Cartographer

Brownfield Cartographer analyzes an existing codebase and produces JSON graph artifacts for:

- module-level import relationships
- data-lineage relationships across Python pipelines, SQL, dbt, and Airflow assets

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

These files are created in the analyzed repository.

## What gets analyzed

- Python imports and module relationships
- Python data reads, writes, and SQL execution paths
- SQL lineage and write targets
- dbt schema metadata and dependencies
- Airflow DAG task topology

## Notes

- Remote repositories are cloned into a temporary directory under `/tmp` for the duration of the run.
- The analyzed repository must be cloneable with your local `git` configuration.
- If a repository has no SQL or dbt assets, `.cartography/lineage_graph.json` may be empty.
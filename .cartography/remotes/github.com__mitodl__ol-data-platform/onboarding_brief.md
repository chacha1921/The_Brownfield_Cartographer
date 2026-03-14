# onboarding_brief

This brief summarizes the semantic synthesis for a new forward-deployed engineer joining the codebase.
Citations below are propagated directly from Semanticist day-one answers to keep downstream references stable for AI-assisted onboarding.

## What business capability does this codebase primarily support?
This codebase primarily supports the comprehensive orchestration, transformation, and analysis of educational data sourced from various learning platforms. It facilitates the ingestion of raw data from systems like Open edX and Canvas, processes it through a dbt-based data warehouse, and then exposes it for analytical purposes, including specialized functions such as student risk probability assessment and B2B organization reporting.

Evidence:
- dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/loads.py:L1-L30 via llm-inference

## Which modules and workflows should a new engineer read first to understand the system's critical path?
To understand the system's critical path, a new engineer should prioritize these modules and workflows:
1.  `dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/loads.py`: This module is fundamental for grasping how raw EdX.org S3 data is ingested and incrementally loaded using the `dlt` framework, representing a major data entry point.
2.  `dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/dagster_assets.py`: It demonstrates the process of wrapping `dlt` resources into Dagster assets, establishing data dependencies and consolidating partitioned raw data into unified tables for subsequent processing.
3.  `bin/dbt-create-staging-models.py`: This command-line utility is essential for automating the generation of dbt source and staging models, a core workflow for integrating new raw data into the data warehouse layer.
4.  `bin/dbt-local-dev.py`: Crucial for local development, this script outlines how AWS Glue Iceberg tables are registered as DuckDB views, enabling efficient local dbt model development against cloud data lakes.
5.  `src/ol_orchestrate/__init__.py`: Although marked as deprecated, its docstring provides a high-level overview of the new modular structure, guiding engineers to the correct locations for shared library code and specific code deployments, which is vital for navigating the overall architecture.

Evidence:
- dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/loads.py:L1-L30 via llm-inference
- dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/dagster_assets.py:L1-L30 via llm-inference
- bin/dbt-create-staging-models.py:L1-L30 via llm-inference
- bin/dbt-local-dev.py:L1-L30 via llm-inference
- src/ol_orchestrate/__init__.py:L1-L30 via llm-inference

## Where are the highest-risk change surfaces, and why?
The highest-risk change surfaces are found in modules exhibiting high architectural centrality and those directly responsible for core data ingestion and transformation processes.
1.  `src/ol_orchestrate/__init__.py`: Despite its deprecated status, this module holds a very high PageRank, indicating its central role in the system's import structure. Any changes here could cause widespread import failures across numerous code locations.
2.  `dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/loads.py`: This module is responsible for ingesting raw EdX.org S3 data. Modifications to its logic could directly compromise the integrity and availability of foundational raw data, potentially leading to data corruption or breaking downstream transformations.
3.  `dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/dagster_assets.py`: As the definition point for Dagster assets derived from ingested data, alterations here risk disrupting data lineage, breaking asset dependencies, and causing inconsistencies in the data catalog, resulting in inaccurate or missing data within the warehouse.
4.  `bin/dbt-create-staging-models.py`: This script automates the generation of dbt staging models. Errors introduced in this utility could lead to incorrect schema definitions, data type mismatches, or broken SQL models, propagating critical issues throughout the entire dbt transformation layer.
5.  `dg_deployments/reconcile_edxorg_partitions.py`: This script is crucial for rectifying historical data integrity issues related to `course_id` values. Incorrect changes could reintroduce data quality problems or lead to data loss during reconciliation, severely impacting the reliability of historical data.

Evidence:
- src/ol_orchestrate/__init__.py:L1-L30 via llm-inference
- dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/loads.py:L1-L30 via llm-inference
- dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/dagster_assets.py:L1-L30 via llm-inference
- bin/dbt-create-staging-models.py:L1-L30 via llm-inference
- dg_deployments/reconcile_edxorg_partitions.py:L1-L30 via llm-inference

## How does data enter, move through, and exit the system?
Data enters the system through various ingestion pipelines, primarily from external learning platforms and APIs. Raw data is ingested from sources such as EdX.org S3 archives, Canvas LMS via its API, and Open edX APIs. Configuration data, like Canvas course IDs, is also sourced from Google Sheets. Once ingested, data moves through processing stages where it is loaded into a data lake as partitioned Dagster assets. It then undergoes schema normalization and structuring using dbt models, creating staging, intermediate, and dimensional layers through cleaning, enriching, and aggregation. The processed data exits the system as various analytical datasets and reports, including dimensional models and specific reporting datasets, which are often consumed by business intelligence tools like Superset. Additionally, the system sends notifications to external systems, such as the Learn API, via webhooks upon successful completion of data processing events.

Evidence:
- dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/loads.py:L1-L30 via llm-inference
- dg_projects/data_loading/data_loading/defs/edxorg_s3_ingest/dagster_assets.py:L1-L30 via llm-inference
- bin/dbt-create-staging-models.py:L1-L30 via llm-inference

## What domain architecture map best explains how responsibilities are split across the codebase?
The codebase's architecture is effectively mapped by its domain clusters, which divide responsibilities into distinct areas:
1.  **Data Orchestration**: This domain is responsible for managing the entire lifecycle of data pipelines, encompassing ingestion, processing, and synchronization of data from various educational platforms such as Open edX, Canvas, and MIT Sloan. It handles scheduling, monitoring, and ensuring the correct flow of data.
2.  **Data Access**: This cluster focuses on providing standardized and secure interfaces for interacting with diverse data sources and external APIs. It includes resources for connecting to various databases (e.g., PostgreSQL, BigQuery), cloud storage (S3, GCS), and external services (e.g., Canvas API, GitHub, Vault).
3.  **Data Platform**: This domain comprises the foundational infrastructure and shared components that underpin the data ecosystem. It includes core Dagster assets, jobs, schedules, and utilities essential for managing the data lakehouse, integrating dbt, and supporting general platform operations.
4.  **Analytics Governance**: This area is dedicated to the management and validation of analytical assets, particularly within Apache Superset. It provides tools for exporting, promoting, synchronizing, and validating dashboards, charts, and datasets, thereby ensuring data quality, consistency, and adherence to access policies.
5.  **Unknown**: This category contains modules whose specific business function could not be determined from the available information, often consisting of empty `__init__.py` files or placeholders.

Evidence:
- bin/dbt-create-staging-models.py:L1-L30 via llm-inference
- src/ol_orchestrate/__init__.py:L1-L30 via llm-inference

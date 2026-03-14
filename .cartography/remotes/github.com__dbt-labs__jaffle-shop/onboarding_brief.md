# onboarding_brief

This brief summarizes the semantic synthesis for a new forward-deployed engineer joining the codebase.

## What business capability does this codebase primarily support?
This codebase primarily supports the automated transformation and orchestration of raw e-commerce data into a structured analytical data mart. It enables the creation of refined datasets for business intelligence and reporting, such as customer profiles, product information, and order details.

Evidence:
- .github/workflows/scripts/dbt_cloud_run_job.py:L26-L55 via llm-inference
- .github/workflows/scripts/dbt_cloud_run_job.py:L101-L130 via llm-inference
- models/staging/stg_products.sql:L1-L30 via llm-inference
- models/marts/customers.sql:L26-L55 via llm-inference

## Which modules and workflows should a new engineer read first to understand the system's critical path?
To grasp the system's critical path, a new engineer should first examine `.github/workflows/scripts/dbt_cloud_run_job.py` to understand the job orchestration and monitoring process. Following this, reviewing `models/staging/stg_orders.sql` and `models/staging/stg_order_items.sql` will clarify how raw order data is initially prepared. Finally, `models/marts/customers.sql` demonstrates the aggregation and enrichment of core business entities.

Evidence:
- .github/workflows/scripts/dbt_cloud_run_job.py:L76-L105 via llm-inference
- .github/workflows/scripts/dbt_cloud_run_job.py:L101-L130 via llm-inference
- models/staging/stg_orders.sql:L1-L30 via llm-inference
- models/staging/stg_order_items.sql:L1-L22 via llm-inference
- models/marts/customers.sql:L1-L30 via llm-inference

## Where are the highest-risk change surfaces, and why?
The highest-risk change surface is the `.github/workflows/scripts/dbt_cloud_run_job.py` module, as it serves as the central orchestration hub for all dbt job executions; any modification here could halt the entire data pipeline. Additionally, core staging models like `models/staging/stg_products.sql` and `models/staging/stg_orders.sql` are high-risk, since changes to their schema or fundamental transformations would propagate errors across numerous dependent downstream mart models.

Evidence:
- .github/workflows/scripts/dbt_cloud_run_job.py:L1-L30 via llm-inference
- .github/workflows/scripts/dbt_cloud_run_job.py:L76-L105 via llm-inference
- models/staging/stg_products.sql:L1-L30 via llm-inference
- models/staging/stg_orders.sql:L1-L30 via llm-inference
- models/marts/orders.sql:L1-L30 via llm-inference

## How does data enter, move through, and exit the system?
Data enters the system from raw `ecom` sources, such as `ecom.raw_customers` and `ecom.raw_orders`, which are referenced directly in staging models. The `.github/workflows/scripts/dbt_cloud_run_job.py` script orchestrates the dbt transformations, moving data through staging layers (e.g., `stg_customers`, `stg_orders`) for initial cleaning and standardization. Subsequently, data flows into mart models (e.g., `customers`, `products`) where it is aggregated and enriched, ultimately exiting as refined analytical datasets.

Evidence:
- models/staging/stg_customers.sql:L1-L23 via llm-inference
- models/staging/stg_orders.sql:L1-L30 via llm-inference
- .github/workflows/scripts/dbt_cloud_run_job.py:L76-L105 via llm-inference
- models/marts/customers.sql:L51-L58 via llm-inference
- models/marts/products.sql:L1-L9 via llm-inference

## What domain architecture map best explains how responsibilities are split across the codebase?
The codebase's responsibilities are primarily divided into `orchestration` and data transformation. The `orchestration` domain, encapsulated by the `dbt_cloud_run_job.py` module, manages the programmatic initiation and monitoring of dbt Cloud jobs. The remaining components, structured as dbt models within `models/staging` and `models/marts`, are dedicated to the sequential transformation of raw e-commerce data into clean, aggregated, and business-ready analytical datasets.

Evidence:
- .github/workflows/scripts/dbt_cloud_run_job.py:L26-L55 via llm-inference
- .github/workflows/scripts/dbt_cloud_run_job.py:L76-L105 via llm-inference
- models/staging/stg_products.sql:L1-L30 via llm-inference
- models/marts/customers.sql:L26-L55 via llm-inference

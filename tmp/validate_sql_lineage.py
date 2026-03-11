from analyzers.sql_lineage import extract_sql_dependencies

queries = [
    "INSERT INTO analytics.orders_summary SELECT * FROM raw.orders o JOIN raw.customers c ON o.customer_id = c.id",
    "WITH recent AS (SELECT * FROM raw.orders), joined AS (SELECT * FROM recent JOIN raw.customers c ON recent.customer_id = c.id) INSERT INTO analytics.output_table SELECT * FROM joined",
    "CREATE TABLE analytics.output_table AS SELECT * FROM raw.orders",
]

for query in queries:
    print(extract_sql_dependencies(query))

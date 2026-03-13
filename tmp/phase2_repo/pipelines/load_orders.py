from pathlib import Path

import pandas as pd

SOURCE_PATH = Path("data") / "orders.csv"
WAREHOUSE_QUERY = "SELECT * FROM raw.customers"
UPSERT_SQL = "INSERT INTO analytics.daily_orders SELECT * FROM raw.orders"

orders = pd.read_csv(SOURCE_PATH)
customers = pd.read_sql(WAREHOUSE_QUERY, con=warehouse)
orders.to_parquet("warehouse/orders.parquet")
engine.execute(UPSERT_SQL)

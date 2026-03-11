create table analytics.stg_orders as
select *
from raw.orders
join raw.customers on orders.customer_id = customers.id

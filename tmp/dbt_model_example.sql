select *
from {{ ref('stg_orders') }}
join {{ source('raw', 'customers') }} using (customer_id)
left join {{ ref('stg_orders') }} using (order_id)

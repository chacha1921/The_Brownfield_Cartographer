select *
from {{ ref('stg_orders') }} s
join {{ source('raw', 'customers') }} c on s.customer_id = c.customer_id

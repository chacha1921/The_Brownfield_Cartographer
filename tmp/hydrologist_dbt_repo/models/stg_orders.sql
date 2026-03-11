select *
from {{ source('raw', 'orders') }}
join {{ source('raw', 'customers') }} using (customer_id)

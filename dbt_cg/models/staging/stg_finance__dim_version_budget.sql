select
    (data->>'version_id')::int as version_id,
    data->>'libelle' as libelle,
    (data->>'date_validation')::date as date_validation
from {{ source('raw', 'finance_dim_version_budget') }}

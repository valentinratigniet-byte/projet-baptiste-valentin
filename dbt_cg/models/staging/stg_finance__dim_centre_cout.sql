select
    (data->>'centre_cout_id')::int as centre_cout_id,
    data->>'code' as code,
    data->>'libelle' as libelle,
    data->>'responsable' as responsable,
    (data->>'centre_parent_id')::int as centre_parent_id
from {{ source('raw', 'finance_dim_centre_cout') }}

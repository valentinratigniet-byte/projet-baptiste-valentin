select
    (data->>'compte_id')::int as compte_id,
    data->>'code_compte' as code_compte,
    data->>'libelle' as libelle,
    data->>'nature' as nature
from {{ source('raw', 'finance_dim_compte') }}

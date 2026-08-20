select
    (data->>'client_id')::int as client_id,
    data->>'code' as code,
    data->>'libelle' as libelle,
    data->>'segment' as segment,
    data->>'siret' as siret
from {{ source('raw', 'crm_dim_client') }}

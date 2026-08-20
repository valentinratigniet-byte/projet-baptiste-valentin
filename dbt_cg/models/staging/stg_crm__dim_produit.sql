select
    (data->>'produit_id')::int as produit_id,
    data->>'code' as code,
    data->>'libelle' as libelle,
    data->>'famille' as famille
from {{ source('raw', 'crm_dim_produit') }}

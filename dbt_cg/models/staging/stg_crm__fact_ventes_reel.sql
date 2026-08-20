select
    (data->>'vente_id')::int as vente_id,
    (data->>'date')::date as date_vente,
    (data->>'centre_cout_id')::int as centre_cout_id,
    (data->>'compte_id')::int as compte_id,
    (data->>'produit_id')::int as produit_id,
    (data->>'client_id')::int as client_id,
    (data->>'montant_reel')::numeric as montant_reel,
    (data->>'quantite')::int as quantite,
    'CRM' as source
from {{ source('raw', 'crm_fact_ventes_reel') }}

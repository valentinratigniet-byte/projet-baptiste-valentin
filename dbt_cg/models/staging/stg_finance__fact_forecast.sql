select
    (data->>'forecast_id')::int as forecast_id,
    (data->>'periode_cible')::date as periode_cible,
    (data->>'date_revision')::date as date_revision,
    (data->>'centre_cout_id')::int as centre_cout_id,
    (data->>'compte_id')::int as compte_id,
    (data->>'montant_forecast')::numeric as montant_forecast
from {{ source('raw', 'finance_fact_forecast') }}

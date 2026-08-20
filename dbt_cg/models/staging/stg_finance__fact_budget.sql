select
    (data->>'budget_id')::int as budget_id,
    (data->>'periode')::date as periode,
    (data->>'centre_cout_id')::int as centre_cout_id,
    (data->>'compte_id')::int as compte_id,
    (data->>'version_id')::int as version_id,
    (data->>'montant_budget')::numeric as montant_budget
from {{ source('raw', 'finance_fact_budget') }}

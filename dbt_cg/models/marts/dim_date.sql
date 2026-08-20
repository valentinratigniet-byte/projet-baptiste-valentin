-- Spine de dates via generate_series (natif Postgres, pas besoin de
-- dbt_utils pour une seule table). Couvre large (2023 pour l'ERP legacy,
-- jusqu'à fin du forecast 2027).
with jours as (
    select generate_series('2023-01-01'::date, '2027-12-31'::date, '1 day'::interval)::date as date
)
select
    date,
    extract(year from date)::int as annee,
    extract(month from date)::int as mois,
    extract(quarter from date)::int as trimestre,
    date_trunc('month', date)::date as premier_jour_mois
from jours

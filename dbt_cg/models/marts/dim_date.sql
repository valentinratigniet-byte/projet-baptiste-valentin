-- Spine de dates via generate_series (natif Postgres, pas besoin de
-- dbt_utils pour une seule table). Couvre large (2023 pour l'ERP legacy,
-- jusqu'à fin du forecast 2027).
with jours as (
    select generate_series('2023-01-01'::date, '2027-12-31'::date, '1 day'::interval)::date as date
)
select
    to_char(date, 'YYYYMMDD')::int as date_key,
    date,
    extract(year from date)::int as annee,
    extract(quarter from date)::int as trimestre,
    'Trim ' || extract(quarter from date)::int as trimestre_nom,
    extract(month from date)::int as mois,
    case extract(month from date)
        when 1 then 'Janvier' when 2 then 'Février' when 3 then 'Mars'
        when 4 then 'Avril' when 5 then 'Mai' when 6 then 'Juin'
        when 7 then 'Juillet' when 8 then 'Août' when 9 then 'Septembre'
        when 10 then 'Octobre' when 11 then 'Novembre' when 12 then 'Décembre'
    end as mois_nom,
    to_char(date, 'YYYY-MM') as annee_mois,
    date_trunc('month', date)::date as premier_jour_mois
from jours

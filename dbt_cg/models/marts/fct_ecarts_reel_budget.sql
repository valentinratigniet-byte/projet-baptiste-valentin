-- Le point clé du MCD (docs/MCD.md) : le Réel est transactionnel (jour),
-- le Budget est mensuel par (centre_cout, compte). On agrège le Réel au
-- grain du Budget avant de les rapprocher.

with reel_mensuel as (
    select
        date_trunc('month', date_vente)::date as periode,
        centre_cout_id,
        compte_id,
        sum(montant_reel) as montant_reel
    from {{ ref('fct_ventes_reel') }}
    group by 1, 2, 3
),

budget as (
    select periode, centre_cout_id, compte_id, montant_budget
    from {{ ref('fct_budget') }}
)

select
    coalesce(r.periode, b.periode) as periode,
    coalesce(r.centre_cout_id, b.centre_cout_id) as centre_cout_id,
    coalesce(r.compte_id, b.compte_id) as compte_id,
    r.montant_reel,
    b.montant_budget,
    r.montant_reel - b.montant_budget as ecart,
    case when b.montant_budget is not null and b.montant_budget != 0
         then round(100.0 * (r.montant_reel - b.montant_budget) / b.montant_budget, 1)
         end as ecart_pct
from reel_mensuel r
full outer join budget b
    on r.periode = b.periode
   and r.centre_cout_id = b.centre_cout_id
   and r.compte_id = b.compte_id

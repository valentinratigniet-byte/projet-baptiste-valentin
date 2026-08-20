-- Allocations analytiques : répartit les montants du centre "Non affecté"
-- (CDCC vide dans l'ERP legacy, cf. docs/REFONTE-ERP.md) vers les centres
-- commerciaux réels, au prorata de leur part de CA — clé de répartition
-- classique en contrôle de gestion.
--
-- Limite assumée : le cahier des charges visait des "charges indirectes",
-- mais fct_ventes_reel (l'unique fait "Réel" du modèle) ne contient que du
-- chiffre d'affaires, pas de charges réelles (seul le Budget en a, cf.
-- fct_ecarts_reel_budget). Il n'existe donc aucune charge réelle à
-- ventiler : ce modèle ventile le CA non affecté, pas des charges. Le
-- mécanisme (clé de répartition au prorata) est le même ; l'objet réparti
-- diffère de l'intitulé d'origine — assumé plutôt que masqué.

with ca_par_centre as (
    select centre_cout_id, sum(montant_reel) as ca
    from {{ ref('fct_ventes_reel') }}
    where centre_cout_id != 0
    group by 1
),

total_ca as (
    select sum(ca) as total from ca_par_centre
),

non_affecte as (
    select sum(montant_reel) as montant_a_ventiler
    from {{ ref('fct_ventes_reel') }}
    where centre_cout_id = 0
)

select
    c.centre_cout_id,
    c.ca as ca_propre,
    round(c.ca / t.total, 4) as cle_repartition,
    round(n.montant_a_ventiler * c.ca / t.total, 2) as montant_alloue
from ca_par_centre c
cross join total_ca t
cross join non_affecte n
order by montant_alloue desc

-- Union CRM + ERP legacy migré, colonne `source` conservée pour traçabilité
-- (engagement pris dans docs/REFONTE-ERP.md §3 Phase 5).
--
-- Limite assumée (dette technique) : le plan comptable ERP (CDCPT, style
-- PCG à 6 chiffres : 706100/707000/758000) n'a jamais été mappé compte par
-- compte vers le plan cible (dim_compte, codes 4 chiffres inventés pour ce
-- portfolio) — une vraie migration produirait cette table de correspondance
-- complète. Ici, les 3 codes CDCPT observés sont tous des comptes de vente
-- (cf. diagnostic ERP), donc mappés vers l'unique compte "Ventes produits"
-- du CRM. Pas de perte d'information sur le sens (vente), une perte de
-- granularité analytique (706100 vs 707000 vs 758000) assumée.

with ventes_crm as (
    select
        vente_id::varchar as id_ligne,
        date_vente,
        centre_cout_id,
        compte_id,
        produit_id,
        client_id,
        montant_reel,
        source
    from {{ ref('stg_crm__fact_ventes_reel') }}
),

compte_ventes as (
    select compte_id from {{ ref('dim_compte') }} where libelle = 'Ventes produits'
),

ventes_erp as (
    select
        e.numpce as id_ligne,
        e.date_piece as date_vente,
        coalesce(cc.centre_cout_id, 0) as centre_cout_id,
        cv.compte_id,
        cast(null as int) as produit_id,  -- l'ERP legacy ne détaille pas le produit
        e.client_crm_id_propose as client_id,
        e.montant_ht as montant_reel,
        e.source
    from {{ ref('stg_erp__fact_ventes_migre') }} e
    left join {{ ref('dim_centre_cout') }} cc on cc.libelle = e.centre_cout_libelle
    cross join compte_ventes cv
)

select * from ventes_crm
union all
select * from ventes_erp

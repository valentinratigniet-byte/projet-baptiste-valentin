-- Passthrough quasi 1:1 : erp_migre est déjà typé (chargé directement en
-- Postgres par erp-legacy/migrate_erp_to_target.py, Sprint 2). La
-- résolution centre_cout_libelle/compte_code -> IDs cible se fait dans
-- marts/fct_ventes_reel.sql (logique métier, pas du staging).
select
    numpce,
    cdcli,
    client_crm_id_propose,
    score_matching,
    centre_cout_libelle,
    compte_code,
    date_piece,
    montant_ht,
    'ERP_LEGACY' as source
from {{ source('erp_migre', 'fact_ventes_erp_migre') }}
where ligne_valide = true
  and client_crm_id_propose is not null  -- seules les lignes réconciliées à un client CRM entrent dans le fait unifié

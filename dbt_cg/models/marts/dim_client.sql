-- MDM / golden record : fusionne le référentiel CRM (source de vérité) avec
-- les clients legacy jamais réconciliés (client_crm_id_propose NULL dans
-- erp_migre.client_reconciliation -> soit un vrai client jamais repris dans
-- le CRM, soit un faux négatif du matching, cf. docs/REFONTE-ERP.md §4).
-- Ces clients legacy-only reçoivent un nouvel ID (10000+) : ils n'existaient
-- dans aucun référentiel cible avant cette fusion.

with crm as (
    select
        client_id,
        code,
        libelle,
        segment,
        siret,
        'CRM' as source
    from {{ ref('stg_crm__dim_client') }}
),

legacy_non_reconcilies as (
    select distinct on (rscli)
        rscli,
        cdcli
    from {{ source('erp_migre', 'client_reconciliation') }}
    where client_crm_id_propose is null
    order by rscli, cdcli
),

legacy_golden as (
    select
        10000 + row_number() over (order by cdcli) as client_id,
        cdcli as code,
        rscli as libelle,
        cast(null as varchar) as segment,
        cast(null as varchar) as siret,
        'ERP_LEGACY_ONLY' as source
    from legacy_non_reconcilies
)

select * from crm
union all
select * from legacy_golden

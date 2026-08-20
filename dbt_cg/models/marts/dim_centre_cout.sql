-- Ajoute un centre "Non affecté" synthétique : cible des lignes ERP legacy
-- dont le CDCC était vide (docs/REFONTE-ERP.md). Sans cette ligne, ces
-- montants n'auraient aucune clé de jointure valide dans les faits.
select * from {{ ref('stg_finance__dim_centre_cout') }}
union all
select 0 as centre_cout_id, 'CC000' as code, 'Non affecté' as libelle,
       cast(null as varchar) as responsable, cast(null as int) as centre_parent_id

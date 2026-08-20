# Data Contracts, qualité & anonymisation RGPD (Sprint 3)

Pipeline : `data-contracts/ingest_to_bronze.py`. Chaque flux source est lu,
anonymisé si besoin, validé contre un contrat JSON Schema
(`data-contracts/schemas/`), puis routé vers MinIO : `bronze/<flux>/` si
conforme, `rejects/<flux>/` (Dead-Letter-Queue) sinon, avec le motif exact.

## Catalogue des flux

| Flux | Source | Schéma | Résultat (dernier run) |
|---|---|---|---|
| `crm/dim_client` | MySQL | `dim_client.schema.json` | 500 acceptés, 0 rejeté |
| `crm/dim_produit` | MySQL | `dim_produit.schema.json` | 200 acceptés, 0 rejeté |
| `crm/fact_ventes_reel` | MySQL | `fact_ventes_reel.schema.json` | 4 442 acceptés, 0 rejeté |
| `logs/app_events` | MongoDB | `app_events.schema.json` | 23 841 acceptés, 0 rejeté |
| `finance/dim_centre_cout` | CSV | `dim_centre_cout.schema.json` | 15 acceptés (anonymisé), 0 rejeté |
| `finance/dim_compte` | CSV | `dim_compte.schema.json` | 40 acceptés, 0 rejeté |
| `finance/dim_version_budget` | CSV | `dim_version_budget.schema.json` | 2 acceptés, 0 rejeté |
| `finance/fact_budget` | CSV | `fact_budget.schema.json` | 2 160 acceptés, 0 rejeté |
| `finance/fact_forecast` | CSV | `fact_forecast.schema.json` | 1 620 acceptés, 0 rejeté |
| `erp_legacy/vente_ligne_brute` | CSV (ERP legacy) | `erp_vente_ligne.schema.json` | 2 449 acceptés, **51 rejetés** |

Les 51 rejets ERP sont exactement les lignes à `DTPCE="00/00/0000"`
identifiées dans le diagnostic du Sprint 2 (`docs/REFONTE-ERP.md`) — le
contrat formalise ce qui était fait à la main en ad-hoc.

**Note d'architecture** : le contrat ERP valide la *structure* du flux brut
(bon format de date, bons patterns), pas sa validité *métier* — c'est le
rôle du script de migration (`erp-legacy/migrate_erp_to_target.py`, Sprint
2) de décider quoi faire d'une ligne structurellement valide mais
métier-discutable (ex. centre de coût vide). Les deux scripts lisent
aujourd'hui le même CSV source indépendamment (dette technique #8) ; ils
seront branchés ensemble (migration lit Bronze) au Sprint 4.

## Classification RGPD

| Champ | Personne physique ? | Décision |
|---|---|---|
| `dim_client.libelle`, `RSCLI` (ERP) | Non — raison sociale d'entreprise (personne morale) | Pas anonymisé. Le RGPD protège les personnes physiques ; une raison sociale B2B n'entre pas dans son périmètre (sauf micro-entrepreneur nommément identifié, non simulé ici) |
| `dim_centre_cout.responsable` | **Oui** — nom d'un salarié | **Anonymisé** par hash SHA-256 irréversible (`anonymize_person`, sel dans `.env` `ANONYMIZATION_SALT`, jamais commit) avant toute écriture, y compris vers la DLQ |
| `logs.session_id`, `user_agent` | Identifiants techniques, pas des données personnelles au sens strict (pas de nom, email, IP) | Pas anonymisé — à revoir si un jour un champ email/IP est ajouté aux logs |

**Choix assumé** : anonymiser uniquement ce qui est réellement une donnée
personnelle plutôt que hasher tout le texte libre par réflexe — hasher les
raisons sociales n'aurait rien protégé (ce ne sont pas des personnes
physiques) et aurait cassé la lisibilité des rapprochements MDM du Sprint 2
sans aucun gain de conformité.

## Où sont les données

```bash
docker exec bv-minio-bronze mc ls local/bronze --recursive
docker exec bv-minio-bronze mc ls local/rejects --recursive
docker exec bv-minio-bronze mc cat local/rejects/erp_legacy/vente_ligne_brute/<timestamp>.jsonl
```

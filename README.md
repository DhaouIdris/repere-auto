# Repère Auto

Observatoire privé des **prix demandés** de voitures d'occasion en France métropolitaine. Implémentation originale Python/SQLite et HTML/CSS/JavaScript, écrite à partir du besoin fonctionnel. Aucun fichier de code, média, fixture ou module du dépôt canadien n'est repris.

## Démarrer en une commande

Python **3.12 ou ultérieur**, depuis ce dossier :

```sh
python -m repere demo
```

Ouvrir **http://127.0.0.1:8080**, puis saisir le code temporaire affiché dans le terminal. La démo n'a aucune dépendance Python externe. Utiliser `python3` si nécessaire sur votre système. Un autre port est possible : `python -m repere demo --port 8090`.

Le serveur de cette commande est réservé au développement local. Il contient 100 annonces entièrement synthétiques, dont des republications et des cas dégradés ; elles correspondent à 94 groupes de véhicules probables et 6 écarts retenus lors du premier chargement. Relancer `demo` rafraîchit les dates synthétiques ; cela ne représente aucune actualisation de marché.

## Connecter des annonces réelles

Le connecteur **Apify** lit les résultats de tâches de scraping terminées pour Leboncoin, La Centrale, AutoScout24 et ParuVendu. Les champs structurés usuels français/anglais et les attributs Leboncoin sont normalisés ; `field_map` permet d'adapter le format d'un scraper. Aucun abonnement, jeton ni droit d'extraction n'est fourni. Les scrapers sont exécutés et planifiés chez le fournisseur ; Repère Auto ne démarre aucune tâche payante.

Après avoir configuré une tâche et vérifié les droits d'accès/réutilisation, sous **PowerShell** :

```powershell
Copy-Item examples/collectors.apify.example.json collectors.local.json
notepad collectors.local.json
# Activer la source choisie et renseigner task_id, authorized et rights_reference.
$env:APIFY_TOKEN = Read-Host "Jeton API Apify"
py -m repere collect --config collectors.local.json --check
py -m repere live --config collectors.local.json
```

Ouvrir l'URL et saisir le nouveau code temporaire affichés dans le terminal. La base réelle `data/repere-import.sqlite` est distincte de la démo. Le serveur lit Apify au démarrage puis toutes les 15 minutes ; la fréquence du scraper lui-même se règle dans Apify. Pour une seule synchronisation : `py -m repere collect --config collectors.local.json`.

**Une clé Apify ne constitue pas une autorisation des marketplaces.** Les connecteurs ne sont pas validés sur un compte ni sur des annonces réelles dans cette livraison. Les tests utilisent des réponses synthétiques. Lire le [guide de connexion](docs/COLLECTORS.md), notamment les limites de format, de coût et de comparabilité. Les annonces collectées apparaissent dans **Explorer les annonces** même lorsqu'aucune estimation ne peut être calculée.

## Ce qui fonctionne

- Tableau de bord responsive en français, recherche, fiche détaillée, références, quartiles, sensibilité et historique de prix.
- Normalisation française, valeurs manquantes explicites, validation JSON/CSV, provenance obligatoire et données démo séparées des imports réels.
- Identités déterministes, clé `(source, source_id)`, regroupement conservateur de doublons probables, ingestion idempotente et historique des changements.
- Baseline médiane entre même marque, modèle, génération, finition, moteur, énergie, boîte, vendeur et région ; fenêtres d'année et kilomètres. Le candidat et son groupe ne servent jamais à sa propre estimation.
- Recherches privées sauvegardées et outbox d'alertes avec cooldown, baisse significative, reprises bornées et revendication atomique. Le bouton de simulation n'envoie rien et ne consomme pas les futurs envois réels.
- Transport Telegram optionnel, désactivé par défaut ; santé, readiness, métriques privées, sauvegarde et rétention.
- Tests Python, test HTTP Gunicorn et parcours navigateur, dépendances verrouillées, configuration Docker et CI fournie.

## Limites à connaître

**Aucun scraper direct des marketplaces ni accès partenaire n'est livré.** Le raccordement aux résultats d'un scraper externe passe par l'API officielle Apify et nécessite votre configuration et vos droits. Une source sans configuration demeure indisponible. Les contacts, VIN, plaques, descriptions et photos du scraper ne sont pas importés. Les imports manuels de textes gardent leur expurgation élémentaire, sans garantie d'anonymisation complète.

Le service est **mono-utilisateur**, limité à 2 000 annonces par base, sans prétention de disponibilité élevée. Les doublons sont probables, pas prouvés ; les faux rapprochements et doublons non détectés restent possibles. La « confiance » est une catégorie descriptive fondée sur l'effectif et la dispersion ; les quartiles ne sont pas des intervalles calibrés. Aucun modèle n'a été validé sur un jeu réel autorisé. Les coûts de réparation, immatriculation et possession ne sont pas inclus.

L'analyse d'images par IA est désactivée et non implémentée ; seules des références d'images explicitement autorisées peuvent être conservées. Aucun compte cloud ni envoi Telegram réel n'a été utilisé pour les validations locales. Lire [VALIDATION.md](docs/VALIDATION.md) pour les vérifications réellement terminées et les contrôles indisponibles.

## Import et exploitation

```sh
python -m repere --db data/repere-import.sqlite --mode import init
# Remplacer cet exemple par un export réel dont vous avez les droits :
python -m repere --db data/repere-import.sqlite --mode import import votre-export.json
python -m repere --db data/repere-demo.sqlite backup backups/demo-01.sqlite
python -m repere --db data/repere-demo.sqlite prune --days 90
```

Les exemples du dossier `examples/` restent **synthétiques**, avec `source: demo`, et doivent donc être utilisés avec une base démo. Pour un import réel, consulter le contrat et les exigences de provenance dans [DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Documentation

- [PHASE1_VALIDATION.md](docs/PHASE1_VALIDATION.md) — correctifs de fiabilité, migration v2 et nouvelles preuves de validation.
- [LOCAL_SETUP.md](docs/LOCAL_SETUP.md) — lancement, import, tests et variables.
- [COLLECTORS.md](docs/COLLECTORS.md) — annonces réelles, tâches Apify, configuration Windows et validation.
- [ARCHITECTURE_AUDIT.md](docs/ARCHITECTURE_AUDIT.md) — décisions et architecture originale.
- [MIGRATION_PLAN.md](docs/MIGRATION_PLAN.md) — correspondance avec le cahier des charges et suites à donner.
- [SOURCE_COMPLIANCE.md](docs/SOURCE_COMPLIANCE.md) — sources, droits et décisions d'accès.
- [DEPLOYMENT.md](docs/DEPLOYMENT.md), [OPERATIONS.md](docs/OPERATIONS.md), [SECURITY.md](docs/SECURITY.md).
- [VALUATION.md](docs/VALUATION.md) — comparabilité, abstention et évaluation temporelle.

## Licence

Le code nouveau de ce dossier est fourni sous licence MIT, voir `LICENSE`. Les dépendances conservent leurs licences propres. Aucun droit sur le dépôt canadien ni sur les annonces des marketplaces n'est accordé par cette licence. Ce projet n'est affilié à aucune plateforme.

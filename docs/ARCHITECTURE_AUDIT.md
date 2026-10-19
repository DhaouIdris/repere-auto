# Architecture de l'implémentation originale

État au 19 octobre 2026. Le dépôt canadien a été inspecté lors de l'audit précédent, mais son code n'est ni importé ni modifié dans ce projet. Il ne s'agit donc pas d'une procédure « clean room » où les développeurs n'auraient jamais vu la source. Les nouveaux fichiers sont écrits séparément à partir des exigences, avec un contrat et une architecture propres. Aucune garantie juridique générale d'originalité n'est déduite d'un simple changement de langage.

## Choix de pile

Python 3.12 et SQLite permettent un prototype local réellement exécutable et testable, sans dépendance applicative externe. Le calcul robuste ne justifie pas ici deux langages ni une pile ML. Une application WSGI permet de remplacer le serveur local de référence par Gunicorn en exploitation. Le navigateur utilise les API natives et un code DOM sans framework. Les outils Playwright/Chromium sont des dépendances de test seulement.

Cloudflare Workers/D1 n'est pas conservé : cela aurait nécessité réutiliser ou réécrire un backend WASM et un protocole de réplication sans bénéfice démontré pour un usage privé de petite taille. La configuration d'exploitation est une application conteneurisée avec SQLite sur disque persistant et proxy TLS. La démo reste utilisable sans cloud.

## Organisation

| Élément | Responsabilité |
|---|---|
| `model.py` | Types, normalisation, dates, validation, identités et rapprochement conservateur |
| `adapters.py` | Contrat d'adaptateur, JSON strict, CSV, provenance et registre des sources |
| `db.py`, `migrations/` | Schéma versionné, transactions, historique, sauvegarde et rétention |
| `valuation.py` | Comparabilité, médiane, quartiles, abstention, sensibilité, filtres et rayon |
| `evaluation.py` | Holdout temporel avec groupes distincts et métriques d'erreur |
| `alerts.py` | Outbox, déduplication des événements, cooldown et transports |
| `web.py` | API privée, cookies signés, CSRF, validation et fichiers statiques |
| `config.py`, `__main__.py` | Configuration validée et commandes locales |
| `static/` | Écrans dashboard, exploration, détails, recherches et sources/imports |
| `tests/`, `scripts/` | Tests métier/intégration, HTTP réel et parcours navigateur |

## Flux

Une enveloppe d'import est validée intégralement avant écriture. Les annonces sont normalisées puis insérées dans une transaction immédiate. Une clé source et un groupe de véhicule probable sont distincts. Un changement de prix crée une nouvelle observation. Les données chronologiquement plus anciennes n'écrasent pas les nouvelles.

Le classement utilise le pool entier du mode courant comme référence, indépendamment des filtres d'affichage. Un index de signature limite les candidats à comparer. Chaque estimation retire le groupe complet du véhicule évalué. Les filtres et la pagination sont bornés, et la capacité de base est explicitement limitée à 2 000 annonces.

Les recherches enregistrées construisent une outbox transactionnelle. La livraison revendique une seule ligne à la fois et met à jour cette seule ligne. Les événements sont distincts des tentatives de livraison. Les ambiguïtés réseau et les crashs autour d'un effet externe empêchent une promesse « exactement une fois » ; voir OPERATIONS.md.

## Surface HTTP

`GET /health`, `/ready`, `/api/session` et la coquille HTML sont accessibles sans données privées. Le reste de l'API exige le bearer ou une session signée. Routes : `/api/listings`, `/api/listings/{id}`, `/api/import`, `/api/searches`, `/api/searches/{id}`, `/api/alerts`, `/api/run-alerts`, `/api/sources`, `/api/summary`, `/api/metrics`. Les écritures par cookie exigent un jeton CSRF et une origine cohérente. Le bouton `/api/run-alerts` utilise exclusivement une prévisualisation locale.

## Limites explicites

Mono-utilisateur ; aucun compte indépendant ni RBAC multi-utilisateur. Les recherches ont un propriétaire fixe, et ne constituent pas un système de tenants. Pas de crawler actif, d'import distant, de file de messages distribuée, d'analyse mécanique ou d'image IA. Pas de modèle transactionnel entraîné sur un marché réel. La base originale ne fournit ni multi-machine, ni chiffrement disque, ni haute disponibilité. Ces limites sont des décisions de MVP, pas des fonctions cachées déjà livrées.

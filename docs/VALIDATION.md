# Validation effectivement réalisée

Ce document conserve les résultats de la livraison initiale. Les correctifs et nouvelles vérifications de la phase 1 sont décrits dans [PHASE1_VALIDATION.md](PHASE1_VALIDATION.md).

Date : **19 octobre 2026**. Application originale Repère Auto 0.1.0. Python 3.12.14, Node 24.19.0, Gunicorn 26.2.0. Playwright 1.62.1 pilotant un Chromium de test 153.0.0 sur Linux.

## Résultats finaux

| Contrôle exécuté | Résultat |
|---|---|
| `python -m unittest discover -v` | **51 tests réussis**, dernière exécution environ 2,64 s |
| `node --check static/app.js` | Réussi, aucune erreur de syntaxe |
| `python scripts/http_smoke.py` avec Gunicorn installé | Réussi : vrai serveur TCP, readiness, API authentifiée, refus anonyme et assets statiques |
| `node scripts/browser-smoke.cjs` | **8 groupes de contrôles réussis** : desktop, fiche, filtres/recherche, simulation/journal, sources indisponibles, session/reload, mobile, déconnexion ; aucune erreur JavaScript capturée |
| Inspection des captures desktop 1440 px et mobile 390 px | Réalisée ; table mobile avec défilement interne, aucun débordement global dans le test |
| `pip-audit --strict --require-hashes -r requirements.lock --format json` | Aucune vulnérabilité connue signalée pour Gunicorn 26.2.0 et packaging 24.2 à cette date |
| `npm audit --audit-level=high --json` | Code retour 0, aucune vulnérabilité signalée dans les dépendances de test au moment du contrôle |
| Parsing YAML de Compose et des deux workflows | Réussi ; cela ne remplace pas une exécution Docker ou GitHub Actions |
| `python scripts/benchmark.py` | 2 000 enregistrements synthétiques classés en **2,804 s** lors d'une exécution locale |

Les comptes rendus locaux sont dans `docs/validation/`. Aucun nombre de couverture n'est revendiqué. Le scan de dépendances est une recherche de vulnérabilités connues, pas un audit de sécurité exhaustif. Les captures de navigateur utilisées pour l'inspection ne sont pas incluses comme livrables.

Le lancement depuis l’archive décompressée a aussi été vérifié avec Python seul : serveur de démo, API protégée, 94 groupes et six opportunités synthétiques.

## Étendue des tests

Normalisation et prix français, types invalides, champs absents, dates futures/naïves, provenance, schéma inconnu, JSON malformé/dupliqué, CSV, URLs sûres, refus d'identifiants personnels, expurgation de texte et séparation démo/réel. Ingestion/historique idempotents, changement de prix, observation ancienne, contraintes de capacité et regroupement conservateur.

Référence sans candidat ni doublons, signature incompatible, groupe rare, dispersion excessive, dommages/financement/fraîcheur, calcul de remise et sensibilité vérifiée contre des suppressions exhaustives. Filtres géographiques et budget, validation temporelle avec groupes disjoints, métriques synthétiques et abstention.

Sessions, CSRF, origine, cookie forgé/expiré, rate limit de connexion, limites de corps, refus anonyme, recherche privée et suppression. Outbox idempotente, succès partiels, reprise après échec, cooldown, credentials expirés simulés et deux drainages concurrents. Backup/restauration et suppression de l'historique par cascade.

## Parcours complet

Ingestion de 100 annonces synthétiques → stockage SQLite → regroupement en 94 véhicules probables → estimation → six opportunités selon les critères → affichage navigateur → filtre Toyota → recherche sauvegardée → alerte en prévisualisation → journal. L'ingestion et la valorisation sont testées dans l'API ; le navigateur utilise le même serveur Gunicorn et des données synthétiques. Aucun message n'est envoyé à l'extérieur.

## Contraintes et contrôles non exécutés

- **Docker absent** de cet environnement : image, healthcheck conteneur, permissions du volume, proxy Caddy et TLS non exécutés. Le YAML est parsable, sans affirmation de déploiement réussi.
- Workflows écrits mais **non lancés sur GitHub** ; aucun registre ni dépôt distant créé. Le scan Trivy de l'image n'a donc pas été réalisé localement.
- Aucun compte hébergeur, domaine, certificat ou service de supervision externe configuré. Aucun déploiement public, staging ou production réalisé.
- Aucun connecteur live de marketplace, aucune donnée réelle collectée/importée, aucun contrat de flux validé.
- Transport Telegram écrit ; tests de livraison avec faux transports. **Aucun envoi Telegram réel ni vérification des credentials d'un compte réel.**
- Aucune analyse IA d'images, aucun benchmark sur des transactions réelles, aucun audit juridique ou d'intrusion indépendant.

Le téléchargement standard de Chromium par Playwright a d'abord échoué sur une archive invalide. Le parcours a ensuite été validé avec le binaire du paquet de test Chromium, extrait sans modification de propriétaire de fichiers, puis passé à `CHROMIUM_EXECUTABLE`. Ce contournement concerne uniquement l'installation locale d'un navigateur de test, aucune restriction d'une marketplace.

## Portée de la mesure de performance

Le workload de 2 000 lignes réutilise six signatures mécaniques synthétiques ; ce n'est ni une mesure de débit concurrent, ni une distribution représentative d'annonces françaises. Le temps mesure le classement en mémoire, sans réseau ni affichage navigateur. Un premier essai avait pris environ 30,5 s ; la recherche de la sensibilité a été réduite à deux médianes extrêmes exactes, les signatures indexées et les détails de références retirés des listes synthétiques de classement. Les tests de non-régression vérifient le même intervalle de sensibilité.

La capacité de 2 000 lignes est une borne de MVP, pas une garantie de latence. Mesurer l'hébergement cible et tester la restauration réelle avant mise en service.
